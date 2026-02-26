import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import CurrentUser, get_current_org_membership, require_org_admin
from app.config import settings
from app.database import get_db
from app.models.conversation import Conversation, Message
from app.models.organization import Invitation, OrgEmployee, Organization, OrganizationMember
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.schemas.organization import (
    InvitationOut,
    InviteCreate,
    MemberOut,
    OrgEmployeeCreate,
    OrgEmployeeOut,
    OrganizationCreate,
    OrganizationOut,
    OrganizationUpdate,
    PersonOut,
    SectionResponse,
    WorkEmailUpdate,
)
from app.services.ai_service import detect_connectors, fetch_all_connector_data, stream_chat_response
from app.services.cache_service import (
    get_section_cache,
    invalidate_member_cache,
    store_section_cache,
)
from app.services.email_service import send_invitation_email
from app.services.integration_service import (
    SECTION_CONNECTOR_KEYS,
    is_connector_connected,
    load_connected_integrations,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: OrganizationCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationOut:
    """Create a new organization. The creator becomes org_admin."""
    existing = await db.execute(select(Organization).where(Organization.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Slug already taken")

    org = Organization(name=body.name, slug=body.slug)
    db.add(org)
    await db.flush()

    member = OrganizationMember(
        org_id=org.id,
        user_id=current_user.id,
        role="org_admin",
        invited_by=current_user.id,
    )
    db.add(member)
    await db.flush()
    return OrganizationOut.model_validate(org)


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(
    org_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationOut:
    await get_current_org_membership(str(org_id), current_user, db)
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrganizationOut.model_validate(org)


@router.patch("/{org_id}", response_model=OrganizationOut)
async def update_organization(
    org_id: uuid.UUID,
    body: OrganizationUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationOut:
    await require_org_admin(str(org_id), current_user, db)
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if body.name is not None:
        org.name = body.name
    if body.settings is not None:
        org.settings = body.settings
    await db.flush()
    return OrganizationOut.model_validate(org)


# ── Members ───────────────────────────────────────────────────────────────────

def _dispatch_precache(org_id_str: str) -> None:
    """Fire-and-forget Celery task dispatch. Runs in a BackgroundTask after response is sent."""
    try:
        from app.tasks.member_sync import precache_org_members
        precache_org_members.delay(org_id_str)
    except Exception:
        pass


@router.get("/{org_id}/members", response_model=list[MemberOut])
async def list_members(
    org_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> list[MemberOut]:
    await get_current_org_membership(str(org_id), current_user, db)
    result = await db.execute(
        select(OrganizationMember)
        .options(selectinload(OrganizationMember.user))
        .where(OrganizationMember.org_id == org_id)
    )
    members = result.scalars().all()

    # Dispatch pre-caching AFTER the response is sent — never blocks the request
    background_tasks.add_task(_dispatch_precache, str(org_id))

    return [
        MemberOut(
            id=m.id,
            user_id=m.user_id,
            email=m.user.email,
            first_name=m.user.first_name,
            last_name=m.user.last_name,
            avatar_url=m.user.avatar_url,
            role=m.role,
            is_active=m.is_active,
            work_email=m.work_email,
            joined_at=m.joined_at,
        )
        for m in members
    ]


@router.get("/{org_id}/people", response_model=list[PersonOut])
async def list_people(
    org_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> list[PersonOut]:
    """Unified people directory combining OrganizationMembers and OrgEmployees."""
    await get_current_org_membership(str(org_id), current_user, db)

    member_result = await db.execute(
        select(OrganizationMember)
        .options(selectinload(OrganizationMember.user))
        .where(OrganizationMember.org_id == org_id)
    )
    employee_result = await db.execute(
        select(OrgEmployee).where(OrgEmployee.org_id == org_id).order_by(OrgEmployee.name)
    )

    people: list[PersonOut] = []
    for m in member_result.scalars().all():
        fn = m.user.first_name or ""
        ln = m.user.last_name or ""
        people.append(PersonOut(
            id=m.id,
            person_type="member",
            first_name=fn or None,
            last_name=ln or None,
            display_name=f"{fn} {ln}".strip() or m.user.email or "Unknown",
            email=m.user.email,
            work_email=m.work_email,
            avatar_url=m.user.avatar_url,
            role=m.role,
            is_active=m.is_active,
            joined_at=m.joined_at,
        ))
    for e in employee_result.scalars().all():
        people.append(PersonOut(
            id=e.id,
            person_type="employee",
            first_name=e.name.split()[0] if e.name else None,
            last_name=" ".join(e.name.split()[1:]) if e.name and len(e.name.split()) > 1 else None,
            display_name=e.name,
            email=None,
            work_email=e.work_email,
            avatar_url=None,
            role=None,
            is_active=True,
            joined_at=e.created_at,
        ))

    # Dispatch pre-caching AFTER the response is sent — never blocks the request
    background_tasks.add_task(_dispatch_precache, str(org_id))

    return people


@router.patch("/{org_id}/members/{member_id}/deactivate", response_model=MemberOut)
async def deactivate_member(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemberOut:
    await require_org_admin(str(org_id), current_user, db)
    result = await db.execute(
        select(OrganizationMember)
        .options(selectinload(OrganizationMember.user))
        .where(OrganizationMember.id == member_id, OrganizationMember.org_id == org_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    member.is_active = False
    await db.flush()
    return MemberOut(
        id=member.id,
        user_id=member.user_id,
        email=member.user.email,
        first_name=member.user.first_name,
        last_name=member.user.last_name,
        avatar_url=member.user.avatar_url,
        role=member.role,
        is_active=member.is_active,
        work_email=member.work_email,
        joined_at=member.joined_at,
    )


@router.patch("/{org_id}/members/{member_id}/role")
async def update_member_role(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    role: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    await require_org_admin(str(org_id), current_user, db)
    if role not in ("user", "org_admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id, OrganizationMember.org_id == org_id
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member.role = role
    await db.flush()
    return {"id": str(member.id), "role": member.role}


@router.patch("/{org_id}/members/{member_id}/work-email", response_model=MemberOut)
async def set_member_work_email(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    body: WorkEmailUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemberOut:
    """Set or update the Microsoft 365 work email for an org member."""
    await require_org_admin(str(org_id), current_user, db)
    result = await db.execute(
        select(OrganizationMember)
        .options(selectinload(OrganizationMember.user))
        .where(OrganizationMember.id == member_id, OrganizationMember.org_id == org_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member.work_email = body.work_email
    await db.flush()
    return MemberOut(
        id=member.id,
        user_id=member.user_id,
        email=member.user.email,
        first_name=member.user.first_name,
        last_name=member.user.last_name,
        avatar_url=member.user.avatar_url,
        role=member.role,
        is_active=member.is_active,
        work_email=member.work_email,
        joined_at=member.joined_at,
    )


# ── Invitations ───────────────────────────────────────────────────────────────

@router.post("/{org_id}/invitations", response_model=InvitationOut, status_code=201)
async def invite_user(
    org_id: uuid.UUID,
    body: InviteCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvitationOut:
    await require_org_admin(str(org_id), current_user, db)

    # Check seat limit
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    active_count_result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.org_id == org_id, OrganizationMember.is_active == True  # noqa: E712
        )
    )
    active_members = active_count_result.scalars().all()
    if len(active_members) >= org.max_seats:
        raise HTTPException(status_code=400, detail=f"Seat limit reached ({org.max_seats} seats)")

    token = secrets.token_urlsafe(32)
    invite = Invitation(
        org_id=org_id,
        email=body.email,
        role=body.role,
        invited_by=current_user.id,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invite)
    await db.flush()

    invite_url = f"{settings.FRONTEND_URL}/accept-invite?token={token}"
    await send_invitation_email(
        to_email=body.email,
        org_name=org.name,
        inviter_name=current_user.full_name,
        invite_url=invite_url,
    )

    return InvitationOut.model_validate(invite)


@router.post("/accept-invitation")
async def accept_invitation(
    token: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    result = await db.execute(
        select(Invitation).where(Invitation.token == token, Invitation.accepted_at == None)  # noqa: E711
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found or already accepted")
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation has expired")

    member = OrganizationMember(
        org_id=invite.org_id,
        user_id=current_user.id,
        role=invite.role,
        invited_by=invite.invited_by,
        # Pre-populate work_email from the invitation email (the org/work address)
        work_email=invite.email,
    )
    db.add(member)
    invite.accepted_at = datetime.now(timezone.utc)
    await db.flush()
    return {"org_id": str(invite.org_id), "role": invite.role}


# ── Org Employees (M365 mailbox targets) ─────────────────────────────────────

@router.get("/{org_id}/employees", response_model=list[OrgEmployeeOut])
async def list_employees(
    org_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[OrgEmployeeOut]:
    """List all employees registered for Microsoft 365 email queries."""
    await get_current_org_membership(str(org_id), current_user, db)
    result = await db.execute(
        select(OrgEmployee)
        .where(OrgEmployee.org_id == org_id)
        .order_by(OrgEmployee.name)
    )
    return [OrgEmployeeOut.model_validate(e) for e in result.scalars().all()]


@router.post("/{org_id}/employees", response_model=OrgEmployeeOut, status_code=status.HTTP_201_CREATED)
async def add_employee(
    org_id: uuid.UUID,
    body: OrgEmployeeCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrgEmployeeOut:
    """Add an employee for Microsoft 365 email querying (no AmbyChat account required)."""
    await require_org_admin(str(org_id), current_user, db)
    employee = OrgEmployee(
        org_id=org_id,
        name=body.name,
        work_email=str(body.work_email).lower(),
    )
    db.add(employee)
    await db.flush()
    return OrgEmployeeOut.model_validate(employee)


@router.delete("/{org_id}/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_employee(
    org_id: uuid.UUID,
    employee_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Remove an employee record."""
    await require_org_admin(str(org_id), current_user, db)
    result = await db.execute(
        select(OrgEmployee).where(OrgEmployee.id == employee_id, OrgEmployee.org_id == org_id)
    )
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    await db.delete(employee)
    await db.flush()


# ── Member Profile Sections ───────────────────────────────────────────────────

# Pre-configured queries per section
_SECTION_QUERIES: dict[str, str] = {
    "emails": (
        "Show the latest {limit} emails. "
        "Highlight urgent threads, pending replies, and required action items."
    ),
    "files": (
        "List the latest {limit} OneDrive or Drive files. "
        "Note recently modified documents and any shared or collaborative files."
    ),
    "salesforce": (
        "Show activities, open opportunities, contacts, and accounts related to "
        "{name} ({work_email}). Highlight overdue tasks, hot deals, and key relationships."
    ),
    "meetings": (
        "Show the latest {limit} meeting recordings. "
        "Include transcript summaries, key decisions, and action items for each."
    ),
}

_SECTION_SYSTEM_PROMPTS: dict[str, str] = {
    "emails": (
        "You are summarizing someone's recent emails for a manager or colleague. "
        "Extract the most important themes in 3–5 bullet points: "
        "urgent items, pending action items, key senders, and important threads. "
        "Be concise, specific, and directly actionable. No preamble."
    ),
    "files": (
        "You are summarizing recently active files for a manager or colleague. "
        "Highlight in 3–4 bullet points: recently modified documents, what they likely "
        "contain based on their names, and any that may need attention. "
        "Be concise and actionable. No preamble."
    ),
    "salesforce": (
        "You are summarizing CRM data for a manager or colleague. "
        "In 4–5 bullet points summarize: pipeline health, overdue activities, "
        "key relationships, and anything time-sensitive. "
        "Flag risks and opportunities explicitly. No preamble."
    ),
    "meetings": (
        "You are summarizing recent meeting recordings for a manager or colleague. "
        "In 4–5 bullet points synthesize: recurring meeting themes, key decisions made, "
        "and open action items across all recordings. "
        "Be concise and actionable. No preamble."
    ),
}


async def _fetch_section_live(
    org_id: uuid.UUID,
    work_email: str,
    person_name: str,
    section: str,
    limit: int,
    db: AsyncSession,
) -> SectionResponse:
    """
    Synchronously fetch a section from the connector(s) and generate an AI summary.
    Called on cache miss. Result is stored to cache before returning.
    """
    import litellm

    connector_keys = SECTION_CONNECTOR_KEYS.get(section, [])
    connected = await load_connected_integrations(org_id, db)

    if not is_connector_connected(connected, connector_keys):
        return SectionResponse(connected=False, results=[], limit=limit, cache_status="miss")

    query = _SECTION_QUERIES[section].format(
        limit=settings.CACHE_MAX_ITEMS,
        name=person_name,
        work_email=work_email,
    )

    import asyncio as _asyncio
    from app.services.ai_service import fetch_connector_data

    active = [i for i in connected if i["connector_key"] in connector_keys]
    tasks = []
    connector_key_used = active[0]["connector_key"] if active else "unknown"
    for integration in active:
        creds = dict(integration["credentials"])
        if integration["connector_key"] in ("microsoft365", "onedrive", "teams"):
            creds["target_user"] = work_email
        tasks.append(fetch_connector_data(integration["connector_key"], creds, query))

    results_list = await _asyncio.gather(*tasks)
    all_results = []
    for r in results_list:
        if "error" not in r:
            all_results.extend(r.get("results", []))
            connector_key_used = r.get("connector", connector_key_used)

    # Generate AI summary
    summary: str | None = None
    if all_results:
        data_text = json.dumps(all_results, default=str)[:8000]
        system_prompt = _SECTION_SYSTEM_PROMPTS.get(section, "Summarize this data.")
        try:
            llm_resp = await litellm.acompletion(
                model=settings.DEFAULT_LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Data:\n{data_text}\n\nProvide an actionable summary."},
                ],
                max_tokens=400,
                api_key=settings.OPENAI_API_KEY or settings.ANTHROPIC_API_KEY,
            )
            summary = llm_resp.choices[0].message.content or None
        except Exception:
            pass

    # Store to cache (fire-and-forget style — we're already async so just await)
    try:
        await store_section_cache(
            db=db,
            org_id=org_id,
            work_email=work_email,
            section=section,
            connector_key=connector_key_used,
            results=all_results,
            summary=summary,
        )
    except Exception:
        pass

    from datetime import datetime, timezone
    return SectionResponse(
        connected=True,
        results=all_results[:limit],
        summary=summary,
        limit=limit,
        cached=False,
        fetched_at=datetime.now(timezone.utc),
        cache_status="miss",
    )


async def _get_member_work_info(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[str, str] | None:
    """Return (work_email, display_name) for a member, or None if not found/no work_email."""
    result = await db.execute(
        select(OrganizationMember)
        .options(selectinload(OrganizationMember.user))
        .where(OrganizationMember.id == member_id, OrganizationMember.org_id == org_id)
    )
    m = result.scalar_one_or_none()
    if not m or not m.work_email:
        return None
    name = f"{m.user.first_name or ''} {m.user.last_name or ''}".strip() or m.work_email
    return m.work_email, name


async def _get_employee_work_info(
    org_id: uuid.UUID,
    employee_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[str, str] | None:
    """Return (work_email, display_name) for an employee, or None if not found."""
    result = await db.execute(
        select(OrgEmployee).where(OrgEmployee.id == employee_id, OrgEmployee.org_id == org_id)
    )
    e = result.scalar_one_or_none()
    if not e:
        return None
    return e.work_email, e.name


async def _handle_section_request(
    org_id: uuid.UUID,
    work_email: str,
    person_name: str,
    section: str,
    limit: int,
    db: AsyncSession,
) -> SectionResponse:
    """Core logic: check cache → return immediately or fetch live → background refresh if stale."""
    cached_response, is_stale = await get_section_cache(db, org_id, work_email, section, limit)

    if cached_response is not None:
        if is_stale:
            # Serve stale data immediately; trigger background refresh
            try:
                from app.tasks.member_sync import sync_member_section
                sync_member_section.delay(str(org_id), work_email, person_name, section)
            except Exception:
                pass
        return cached_response

    # Cache miss — fetch live (same latency as before caching was added)
    return await _fetch_section_live(org_id, work_email, person_name, section, limit, db)


def _section_endpoint(section_name: str):
    """Factory that creates a section endpoint handler for member or employee."""
    async def _member_handler(
        org_id: uuid.UUID,
        member_id: uuid.UUID,
        current_user: CurrentUser,
        db: Annotated[AsyncSession, Depends(get_db)],
        limit: int = Query(default=15, ge=1, le=50),
    ) -> SectionResponse:
        await get_current_org_membership(str(org_id), current_user, db)
        info = await _get_member_work_info(org_id, member_id, db)
        if info is None:
            return SectionResponse(
                connected=False,
                results=[],
                limit=limit,
                error="No work email set for this member. Set it in Settings → Members.",
                cache_status="miss",
            )
        work_email, name = info
        return await _handle_section_request(org_id, work_email, name, section_name, limit, db)

    async def _employee_handler(
        org_id: uuid.UUID,
        employee_id: uuid.UUID,
        current_user: CurrentUser,
        db: Annotated[AsyncSession, Depends(get_db)],
        limit: int = Query(default=15, ge=1, le=50),
    ) -> SectionResponse:
        await get_current_org_membership(str(org_id), current_user, db)
        info = await _get_employee_work_info(org_id, employee_id, db)
        if info is None:
            raise HTTPException(status_code=404, detail="Employee not found")
        work_email, name = info
        return await _handle_section_request(org_id, work_email, name, section_name, limit, db)

    return _member_handler, _employee_handler


# Register section endpoints for members and employees
for _section in ("emails", "files", "salesforce", "meetings"):
    _member_fn, _employee_fn = _section_endpoint(_section)
    router.get(
        f"/{{org_id}}/members/{{member_id}}/sections/{_section}",
        response_model=SectionResponse,
        tags=["member-sections"],
    )(_member_fn)
    router.get(
        f"/{{org_id}}/employees/{{employee_id}}/sections/{_section}",
        response_model=SectionResponse,
        tags=["member-sections"],
    )(_employee_fn)


# ── Manual Cache Refresh ──────────────────────────────────────────────────────

def _dispatch_sync_all(org_id_str: str, work_email: str, name: str) -> None:
    """Fire-and-forget: dispatch Celery sync task. Runs after response is sent."""
    try:
        from app.tasks.member_sync import sync_member_all_sections
        sync_member_all_sections.delay(org_id_str, work_email, name)
    except Exception:
        pass


@router.post("/{org_id}/members/{member_id}/refresh", status_code=202)
async def refresh_member_cache(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> dict:
    """Invalidate and re-fetch all cached sections for a member."""
    await get_current_org_membership(str(org_id), current_user, db)
    info = await _get_member_work_info(org_id, member_id, db)
    if info is None:
        raise HTTPException(status_code=400, detail="No work email set for this member.")
    work_email, name = info
    await invalidate_member_cache(db, org_id, work_email)
    background_tasks.add_task(_dispatch_sync_all, str(org_id), work_email, name)
    return {"status": "refreshing"}


@router.post("/{org_id}/employees/{employee_id}/refresh", status_code=202)
async def refresh_employee_cache(
    org_id: uuid.UUID,
    employee_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> dict:
    """Invalidate and re-fetch all cached sections for an employee."""
    await get_current_org_membership(str(org_id), current_user, db)
    info = await _get_employee_work_info(org_id, employee_id, db)
    if info is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    work_email, name = info
    await invalidate_member_cache(db, org_id, work_email)
    background_tasks.add_task(_dispatch_sync_all, str(org_id), work_email, name)
    return {"status": "refreshing"}


# ── Member-Scoped Chat (pinned target_user) ───────────────────────────────────

async def _member_chat_stream(
    org_id: uuid.UUID,
    work_email: str,
    display_name: str,
    body: ChatRequest,
    current_user_id: uuid.UUID,
    db: AsyncSession,
) -> StreamingResponse:
    """Core SSE chat logic with target_user pinned to work_email."""
    if body.conversation_id:
        conv_result = await db.execute(
            select(Conversation).where(
                Conversation.id == body.conversation_id,
                Conversation.user_id == current_user_id,
            )
        )
        conv = conv_result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        msg_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at)
        )
        prior_messages = msg_result.scalars().all()
        history: list[dict] = [{"role": m.role, "content": m.content} for m in prior_messages]
    else:
        conv = Conversation(
            org_id=org_id,
            user_id=current_user_id,
            title=f"[{display_name}] {body.message[:50]}",
        )
        db.add(conv)
        await db.flush()
        history = []

    history.append({"role": "user", "content": body.message})
    user_msg = Message(conversation_id=conv.id, role="user", content=body.message)
    db.add(user_msg)
    await db.flush()

    connected = await load_connected_integrations(org_id, db)
    target_keys = detect_connectors(body.message) or None

    # Override all target_user injections with the pinned email
    for integration in connected:
        if integration["connector_key"] in ("microsoft365", "onedrive", "teams"):
            integration["credentials"]["target_user"] = work_email

    # Build org_members list so the AI context knows who this is
    org_members = [{"first_name": display_name.split()[0], "last_name": "", "work_email": work_email}]

    connector_results = await fetch_all_connector_data(
        connected, body.message, target_keys, org_members=org_members,
        history=history[:-1],
    )

    person_context = (
        f"You are answering questions specifically about {display_name} ({work_email}). "
        "All connector data below is scoped to this person. "
        "Cite sources clearly and be concise."
    )

    async def _event_stream() -> AsyncIterator[bytes]:
        yield f"data: [CONV_ID:{conv.id}]\n\n".encode()
        full_response = []
        async for chunk in stream_chat_response(
            [{"role": "system", "content": person_context}] + history,
            connector_results,
        ):
            full_response.append(chunk)
            yield f"data: {json.dumps(chunk)}\n\n".encode()
        assistant_content = "".join(full_response)
        sources = [r.get("connector") for r in connector_results if "error" not in r]
        assistant_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=assistant_content,
            metadata_={"sources": sources},
        )
        db.add(assistant_msg)
        await db.commit()
        yield b"data: [DONE]\n\n"

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@router.post("/{org_id}/members/{member_id}/chat/stream")
async def member_chat_stream(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    body: ChatRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """SSE chat scoped to a specific member's data (target_user pinned server-side)."""
    await get_current_org_membership(str(org_id), current_user, db)
    info = await _get_member_work_info(org_id, member_id, db)
    if info is None:
        raise HTTPException(status_code=400, detail="No work email set for this member.")
    work_email, name = info
    return await _member_chat_stream(org_id, work_email, name, body, current_user.id, db)


@router.post("/{org_id}/employees/{employee_id}/chat/stream")
async def employee_chat_stream(
    org_id: uuid.UUID,
    employee_id: uuid.UUID,
    body: ChatRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """SSE chat scoped to a specific employee's data (target_user pinned server-side)."""
    await get_current_org_membership(str(org_id), current_user, db)
    info = await _get_employee_work_info(org_id, employee_id, db)
    if info is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    work_email, name = info
    return await _member_chat_stream(org_id, work_email, name, body, current_user.id, db)

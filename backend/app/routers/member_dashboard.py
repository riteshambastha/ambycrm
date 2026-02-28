"""Member dashboard router — all endpoints auto-scoped to the logged-in member's data.

Every query is pinned to the member's work_email as target_user.
Members can never access other people's data through these endpoints.
"""

import json
import uuid
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import CurrentMember
from app.database import get_db
from app.models.conversation import Conversation, Message
from app.models.organization import OrgEmployee, Organization
from app.schemas.chat import ChatRequest, ConversationOut, MessageOut
from app.schemas.organization import SectionResponse
from app.services.ai_service import detect_connectors, fetch_all_connector_data, stream_chat_response
from app.services.integration_service import load_connected_integrations

router = APIRouter(prefix="/member", tags=["member-dashboard"])


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/profile")
async def member_profile(
    member: CurrentMember,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    result = await db.execute(
        select(Organization).where(Organization.id == member.org_id)
    )
    org = result.scalar_one_or_none()
    name_parts = (member.name or "").split()
    return {
        "employee_id": str(member.id),
        "name": member.name,
        "first_name": name_parts[0] if name_parts else None,
        "last_name": " ".join(name_parts[1:]) if len(name_parts) > 1 else None,
        "email": member.work_email,
        "org_id": str(member.org_id),
        "org_name": org.name if org else "Unknown",
    }


# ── Conversations ─────────────────────────────────────────────────────────────

@router.get("/chat/conversations", response_model=list[ConversationOut])
async def list_member_conversations(
    member: CurrentMember,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ConversationOut]:
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.org_id == member.org_id,
            Conversation.employee_id == member.id,
            Conversation.is_archived == False,  # noqa: E712
        )
        .order_by(Conversation.updated_at.desc())
    )
    return [ConversationOut.model_validate(c) for c in result.scalars().all()]


@router.get("/chat/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def get_member_messages(
    conversation_id: uuid.UUID,
    member: CurrentMember,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[MessageOut]:
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(
            Conversation.id == conversation_id,
            Conversation.employee_id == member.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return [
        MessageOut(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            metadata_=m.metadata_,
            created_at=m.created_at,
        )
        for m in conv.messages
    ]


@router.delete("/chat/conversations/{conversation_id}", status_code=204)
async def archive_member_conversation(
    conversation_id: uuid.UUID,
    member: CurrentMember,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.employee_id == member.id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv:
        conv.is_archived = True
        await db.flush()


# ── Streaming Chat ────────────────────────────────────────────────────────────

@router.post("/chat/stream")
async def member_chat_stream(
    body: ChatRequest,
    member: CurrentMember,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """Stream chat response auto-scoped to the member's own data."""
    org_id = member.org_id
    work_email = member.work_email
    display_name = member.name
    conversation_id = body.conversation_id
    message_text = body.message

    async def _event_stream() -> AsyncIterator[bytes]:
        try:
            if conversation_id:
                conv_result = await db.execute(
                    select(Conversation).where(
                        Conversation.id == conversation_id,
                        Conversation.employee_id == member.id,
                    )
                )
                conv = conv_result.scalar_one_or_none()
                if not conv:
                    yield b"data: [ERROR] Conversation not found.\n\n"
                    return
                msg_result = await db.execute(
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.created_at)
                )
                history: list[dict] = [
                    {"role": m.role, "content": m.content}
                    for m in msg_result.scalars().all()
                ]
            else:
                conv = Conversation(
                    org_id=org_id,
                    user_id=None,
                    employee_id=member.id,
                    title=message_text[:60],
                )
                db.add(conv)
                await db.flush()
                history = []

            yield f"data: [CONV_ID:{conv.id}]\n\n".encode()

            history.append({"role": "user", "content": message_text})
            user_msg = Message(conversation_id=conv.id, role="user", content=message_text)
            db.add(user_msg)
            await db.flush()

            # Load connectors and pin target_user to member's email
            connected = await load_connected_integrations(org_id, db)
            target_keys = detect_connectors(message_text) or None

            for integration in connected:
                if integration["connector_key"] in ("microsoft365", "onedrive", "teams", "recall"):
                    integration["credentials"]["target_user"] = work_email

            org_members = [
                {"first_name": display_name.split()[0], "last_name": "", "work_email": work_email}
            ]

            connector_results = await fetch_all_connector_data(
                connected, message_text, target_keys,
                org_members=org_members, history=history[:-1],
            )

            person_context = (
                f"You are answering questions for {display_name} ({work_email}). "
                "All connector data below is scoped to this person's own data. "
                "Cite sources clearly and be concise."
            )

            full_response: list[str] = []
            async for chunk in stream_chat_response(
                [{"role": "system", "content": person_context}] + history,
                connector_results,
            ):
                full_response.append(chunk)
                yield f"data: {json.dumps(chunk)}\n\n".encode()

            assistant_content = "".join(full_response)
            sources = [r.get("connector") for r in connector_results if "error" not in r]
            db.add(Message(
                conversation_id=conv.id,
                role="assistant",
                content=assistant_content or "(no response)",
                metadata_={"sources": sources},
            ))
            await db.commit()

        except Exception as exc:
            yield f"data: [ERROR] {str(exc)}\n\n".encode()
            try:
                await db.rollback()
            except Exception:
                pass

        yield b"data: [DONE]\n\n"

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


# ── Profile Sections ──────────────────────────────────────────────────────────

@router.get("/sections/{section}", response_model=SectionResponse)
async def member_section(
    section: str,
    member: CurrentMember,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=15, ge=1, le=50),
) -> SectionResponse:
    """Get a profile section (emails/files/salesforce/meetings) for the logged-in member."""
    valid_sections = ("emails", "files", "salesforce", "meetings")
    if section not in valid_sections:
        raise HTTPException(status_code=400, detail=f"Invalid section. Must be one of: {', '.join(valid_sections)}")

    # Reuse the same section handler from organizations router
    from app.routers.organizations import _handle_section_request
    return await _handle_section_request(
        member.org_id, member.work_email, member.name, section, limit, db
    )

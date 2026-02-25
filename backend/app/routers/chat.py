"""Chat router — conversations, messages, and streaming AI responses."""

import uuid
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import CurrentUser, get_current_org_membership
from app.database import get_db
from app.models.conversation import Conversation, Message
from app.models.integration import Integration, IntegrationCredential
from app.models.organization import OrgEmployee
from app.schemas.chat import ChatRequest, ConversationOut, MessageOut
from app.services.ai_service import detect_connectors, fetch_all_connector_data, stream_chat_response
from app.services.encryption import decrypt

router = APIRouter(prefix="/chat", tags=["chat"])


# ── Conversations ─────────────────────────────────────────────────────────────

@router.get("/{org_id}/conversations", response_model=list[ConversationOut])
async def list_conversations(
    org_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ConversationOut]:
    await get_current_org_membership(str(org_id), current_user, db)
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.org_id == org_id,
            Conversation.user_id == current_user.id,
            Conversation.is_archived == False,  # noqa: E712
        )
        .order_by(Conversation.updated_at.desc())
    )
    return [ConversationOut.model_validate(c) for c in result.scalars().all()]


@router.get("/{org_id}/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def get_messages(
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[MessageOut]:
    await get_current_org_membership(str(org_id), current_user, db)
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
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


@router.delete("/{org_id}/conversations/{conversation_id}", status_code=204)
async def archive_conversation(
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == current_user.id
        )
    )
    conv = result.scalar_one_or_none()
    if conv:
        conv.is_archived = True


# ── Streaming Chat ────────────────────────────────────────────────────────────

async def _load_connected_integrations(
    org_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> list[dict]:
    """Load all connected integrations with decrypted credentials."""
    result = await db.execute(
        select(Integration)
        .options(selectinload(Integration.credentials))
        .where(Integration.org_id == org_id, Integration.status == "connected")
    )
    integrations = result.scalars().all()
    out = []
    for integration in integrations:
        if not integration.credentials:
            continue
        cred = integration.credentials[0]
        try:
            out.append({
                "connector_key": integration.connector_key,
                "credentials": {
                    "access_token": decrypt(cred.access_token),
                    "refresh_token": decrypt(cred.refresh_token) if cred.refresh_token else None,
                    **cred.raw_data,
                },
            })
        except Exception:
            continue
    return out


@router.post("/{org_id}/stream")
async def stream_chat(
    org_id: uuid.UUID,
    body: ChatRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    await get_current_org_membership(str(org_id), current_user, db)

    # Resolve or create conversation
    if body.conversation_id:
        conv_result = await db.execute(
            select(Conversation).where(
                Conversation.id == body.conversation_id,
                Conversation.user_id == current_user.id,
            )
        )
        conv = conv_result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Explicitly load prior messages — never use lazy loading with asyncpg
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
            user_id=current_user.id,
            title=body.message[:60],
        )
        db.add(conv)
        await db.flush()
        history = []

    # Append the new user message to the history that goes to the LLM
    history.append({"role": "user", "content": body.message})

    # Persist user message
    user_msg = Message(conversation_id=conv.id, role="user", content=body.message)
    db.add(user_msg)
    await db.flush()

    # Fetch connector data
    connected = await _load_connected_integrations(org_id, current_user.id, db)
    target_keys = detect_connectors(body.message) or None

    # Load registered employees so AI service can resolve names → work emails
    employees_result = await db.execute(
        select(OrgEmployee).where(OrgEmployee.org_id == org_id)
    )
    org_members = [
        {
            "first_name": e.name.split()[0] if e.name else "",
            "last_name": " ".join(e.name.split()[1:]) if e.name and len(e.name.split()) > 1 else "",
            "work_email": e.work_email,
        }
        for e in employees_result.scalars().all()
    ]

    connector_results = await fetch_all_connector_data(
        connected, body.message, target_keys, org_members=org_members
    )

    # Accumulate and save the assistant response after streaming
    async def _event_stream() -> AsyncIterator[bytes]:
        full_response = []
        async for chunk in stream_chat_response(history, connector_results):
            full_response.append(chunk)
            yield f"data: {chunk}\n\n".encode()

        # Persist assistant message
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

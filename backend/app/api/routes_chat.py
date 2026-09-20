"""对话相关接口：创建/列出 conversation，SSE 聊天。

`thread_id` 从来不由前端传（对应档案里"前端不发 thread_id、后端默认 '1'"这个
具体缺陷）——前端只知道 `conversation_id`，`thread_id` 是服务端在
`Conversation` 表里生成并维护的内部细节，前端永远看不到、也改不了它。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.sse import stream_graph_turn
from app.auth.dependencies import get_current_user, get_db_session
from app.db.models import User
from app.security.rate_limit import rate_limited_user
from app.sessions.manager import ConversationNotFoundError, ConversationOwnershipError

router = APIRouter(tags=["chat"])


class ConversationCreateRequest(BaseModel):
    title: str = "新对话"


class ConversationResponse(BaseModel):
    id: int
    title: str
    created_at: datetime


class ChatRequest(BaseModel):
    conversation_id: int
    message: str | None = None
    confirm: bool | None = None  # 会话正在等待 HITL 确认时，用这个字段批准/拒绝


def _session_manager(request: Request):
    return request.app.state.session_manager


def _graph(request: Request):
    return request.app.state.graph


def _tracer(request: Request):
    return request.app.state.tracer


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    body: ConversationCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ConversationResponse:
    manager = _session_manager(request)
    conversation = await manager.create_conversation(session, user, title=body.title)
    return ConversationResponse(id=conversation.id, title=conversation.title, created_at=conversation.created_at)


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ConversationResponse]:
    manager = _session_manager(request)
    conversations = await manager.list_conversations(session, user)
    return [
        ConversationResponse(id=c.id, title=c.title, created_at=c.created_at) for c in conversations
    ]


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    user: User = Depends(rate_limited_user),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    manager = _session_manager(request)
    graph = _graph(request)

    try:
        conversation = await manager.get_owned_conversation(session, user, body.conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在") from None
    except ConversationOwnershipError:
        # 故意和"不存在"返回同一种 404，不向调用方泄露"这个 ID 属于别人"这个信息。
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在") from None

    config = {"configurable": {"thread_id": conversation.thread_id}}

    # 归属校验、判断是不是在等确认——这些都要在拿锁之前、用当前请求的 db session 做完，
    # 因为锁会一直握到流式响应真正发完最后一个字节，不能占着锁等 DB 查询。
    snapshot = await graph.aget_state(config)
    is_paused = bool(snapshot.next)

    if is_paused:
        if body.confirm is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该会话正在等待确认，请提交 confirm 字段")
        run_input = Command(resume={"approved": body.confirm})
    else:
        if not body.message:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少 message")
        run_input = {
            "messages": [HumanMessage(content=body.message)],
            "tool_call_queue": [],
            "awaiting_confirmation": None,
        }

    async def event_stream():
        # 锁在 `async with` 里横跨整个 `yield` 过程，直到生成器耗尽才释放——
        # 也就是这个 thread 的下一个请求要等这一轮 SSE 真正推送完才能拿到锁，
        # 不是"拿到第一个事件就放行"。同时客户端仍然是逐条实时收事件，
        # 不需要等全部跑完才能看到第一条。
        async with manager.lock_for_thread(conversation.thread_id):
            async for event in stream_graph_turn(graph, run_input, config):
                yield event

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/conversations/{conversation_id}/trace")
async def get_conversation_trace(
    conversation_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    manager = _session_manager(request)
    try:
        conversation = await manager.get_owned_conversation(session, user, conversation_id)
    except (ConversationNotFoundError, ConversationOwnershipError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在") from None

    return await _tracer(request).spans_for_thread(conversation.thread_id)

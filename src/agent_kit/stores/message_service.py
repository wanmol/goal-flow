"""MessageServiceStore：基于宿主仓库 ``MessageService`` 的 ConversationStore 实现。

设计意图：替代 ``harness/middleware/context_manager.py:ConversationHistoryContextManager``，
迁入 ``stores/`` 与 ``ConversationHistoryMiddleware`` 配对。老
``ConversationHistoryContextManager`` 暂保留，内部委派给本实现，逐步替换。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from agent_kit.stores.base import ConversationStore

logger = logging.getLogger(__name__)


class MessageServiceStore(ConversationStore):
    """基于宿主仓库 ``service.message_service.MessageService`` 的实现。

    构造参数：
    - ``default_scene_type``：``save_turn`` 时 meta 没传 ``scene_type`` 时的默认值
    - ``user_id_field``：从 meta 取 ``creator_id`` / ``last_updater_id`` 的 key 名

    要求宿主仓库的 ``service.message_service.MessageService`` 已经可 import；
    不可用时构造期不报错，调用 ``load_history`` / ``save_turn`` 才报。
    """

    def __init__(
        self,
        *,
        default_scene_type: str = "WANMOL",
        user_id_field: str = "sys_user_id",
    ):
        self._default_scene_type = default_scene_type
        self._user_id_field = user_id_field

    def load_history(self, conversation_id: str) -> list[dict[str, Any]]:
        if not conversation_id:
            return []
        try:
            from service.message_service import MessageService

            history = MessageService.get_llm_template_by_conversation_id(
                conversation_id=conversation_id
            )
            return list(history or [])
        except Exception as e:
            logger.warning(
                "MessageServiceStore.load_history failed",
                extra={"conversation_id": conversation_id, "error": str(e)},
            )
            return []

    def save_turn(
        self,
        conversation_id: str,
        *,
        query: str,
        answer: str,
        **meta: Any,
    ) -> None:
        if not conversation_id or not query:
            return
        try:
            from db.message import Message
            from service.message_service import MessageService

            user_id = meta.get(self._user_id_field) or ""
            MessageService.create(
                Message(
                    conversation_id=conversation_id,
                    query=query,
                    answer=answer or None,
                    message_id=str(uuid.uuid4()),
                    creator_id=user_id,
                    last_updater_id=user_id,
                    scene_type=meta.get("scene_type") or self._default_scene_type,
                    agent_id=meta.get("agent_id") or "",
                )
            )
            logger.info(
                "MessageServiceStore.save_turn ok",
                extra={"conversation_id": conversation_id},
            )
        except Exception as e:
            logger.warning(
                "MessageServiceStore.save_turn failed",
                extra={"conversation_id": conversation_id, "error": str(e)},
            )

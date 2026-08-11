"""MessageServiceStore: a ConversationStore implementation based on the host repo's ``MessageService``.

Design intent: replaces ``harness/middleware/context_manager.py:ConversationHistoryContextManager``,
moved into ``stores/`` and paired with ``ConversationHistoryMiddleware``. The old
``ConversationHistoryContextManager`` is kept for now, internally delegating to this implementation, replaced gradually.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from agent_kit.stores.base import ConversationStore

logger = logging.getLogger(__name__)


class MessageServiceStore(ConversationStore):
    """Implementation based on the host repo's ``service.message_service.MessageService``.

    Constructor parameters:
    - ``default_scene_type``: the default value when meta does not pass ``scene_type`` during ``save_turn``
    - ``user_id_field``: the key name used to get ``creator_id`` / ``last_updater_id`` from meta

    Requires the host repo's ``service.message_service.MessageService`` to be importable;
    when unavailable, no error at construction time -- it only errors when calling ``load_history`` / ``save_turn``.
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

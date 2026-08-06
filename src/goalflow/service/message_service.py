import time
#from uuid_extensions import uuid7
import uuid
from typing import Dict, List

from goalflow.cache.message_cache import MessageCache
from goalflow.model.wf_message import Message
from goalflow.config import get_logger

logger = get_logger(__name__)


class MessageService:
    """
    消息服务
    """

    @staticmethod
    def create(message: Message) -> Message:
        start_time = time.time()
        if not message.conversation_id:
            message.conversation_id = str(uuid.uuid4())
        msg = MessageCache.create(message)
        logger.info(
            f"MessageService create message cost time: {time.time() - start_time}"
        )
        return msg

    @staticmethod
    def update(message: Message) -> Message:
        return MessageCache.update(
            mid=message.id,
            query=message.query,
            answer=message.answer,
            conversation_id=message.conversation_id,
            last_updater_id=message.last_updater_id,
        )

    @staticmethod
    def get_llm_template_by_conversation_id(
        conversation_id: str,
    ) -> List[Dict[str, str]]:
        """
        获取会话历史记录，缓存格式
        """
        return MessageCache.get_llm_template_by_conversation_id(
            conversation_id=conversation_id
        )

    @staticmethod
    def get_by_message_id(message_id: str) -> Message:
        return MessageCache.get_by_message_id(message_id=message_id)

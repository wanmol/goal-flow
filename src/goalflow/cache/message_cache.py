import json
from typing import Dict, List, Optional

from goalflow.infra.base_cache import BaseCache
from goalflow.constants import RedisKeyConstants
from goalflow.infra.database import Config
from goalflow.model.wf_message import Message, MessageDB
from goalflow.infra.redis_manager import redis_client
from goalflow.config import get_logger

logger = get_logger(__name__)


class MessageCache(MessageDB, BaseCache):
    """
    消息缓存类
    """

    config = Config()
    # 数据库分页大小
    limit: int = 25
    # 缓存队列长度
    limit_cache: int = limit * 2 - 1
    # limit = config.MESSAGES_PER_PAGE
    # 缓存时间（秒）
    ttl: int = 3600

    @classmethod
    def _get_key(cls, conversation_id: str) -> str:
        """
        获取消息缓存键
        """
        return f"{RedisKeyConstants.MESSAGE_PREFIX_BY_CONVERSATION_ID}{conversation_id}"

    def _messages_to_llm_template(
        *, conversation_id: str, messages: List[Message]
    ) -> List[Dict[str, str]]:
        """
        消息列表转换为缓存格式
        """
        data = []
        try:
            if messages is not None:
                for message_item in messages:
                    if (
                        message_item.query is None
                        or message_item.query.strip() == ""
                        or message_item.answer is None
                        or message_item.answer.strip() == ""
                    ):
                        continue

                    data.append(
                        json.dumps(
                            {"role": "assistant", "text": message_item.answer},
                            ensure_ascii=False,
                        )
                    )
                    data.append(
                        json.dumps(
                            {"role": "user", "text": message_item.query},
                            ensure_ascii=False,
                        )
                    )

                if data:
                    r_key = MessageCache._get_key(conversation_id)
                    with redis_client.pipeline() as pipe:
                        pipe.rpush(r_key, *data)
                        pipe.ltrim(r_key, 0, MessageCache.limit_cache)
                        pipe.expire(r_key, MessageCache.ttl)
                        pipe.execute()
        except Exception as e:
            logger.error(f"MessageCache._messages_to_llm_template error: {e}")
        return data

    @classmethod
    def _message_to_llm_template(cls, *, message: Message):
        """
        消息转换为缓存格式
        """
        try:
            if BaseCache.has_key(key=MessageCache._get_key(message.conversation_id)):
                # Key存在，说明缓存未过期，消息添加到缓存队列头部
                r_key = MessageCache._get_key(message.conversation_id)

                # 只有当文本不为 answer和 query都不为 None 且不为空字符串时才添加到缓存
                if (message.answer is not None and message.answer.strip()) and (
                    message.query is not None and message.query.strip()
                ):
                    with redis_client.pipeline() as pipe:
                        data_user = json.dumps(
                            {"role": "user", "text": message.query}, ensure_ascii=False
                        )
                        data_assistant = json.dumps(
                            {"role": "assistant", "text": message.answer},
                            ensure_ascii=False,
                        )
                        pipe.lpush(r_key, data_user, data_assistant)
                        pipe.ltrim(r_key, 0, MessageCache.limit_cache)
                        pipe.expire(r_key, MessageCache.ttl)
                        pipe.execute()

            else:
                # Key不存在，需要重新刷新缓存
                message_list = MessageDB.get_by_conversation_id_and_limit(
                    conversation_id=message.conversation_id, limit=MessageCache.limit
                )

                MessageCache._messages_to_llm_template(
                    conversation_id=message.conversation_id, messages=message_list
                )
                # 转换为缓存格式
        except Exception as e:
            logger.error(f"MessageCache._message_to_llm_template error: {e}")
            raise e

    @classmethod
    def create(cls, message: Message) -> Message:
        _message = super().create(message)
        return _message

    @classmethod
    def update(
        cls,
        *,
        mid: int,
        query: str,
        answer: str,
        conversation_id: str,
        last_updater_id: str,
    ) -> Optional[Message]:
        _message = super().update(
            mid=mid,
            query=query,
            answer=answer,
            conversation_id=conversation_id,
            last_updater_id=last_updater_id,
        )

        MessageCache._message_to_llm_template(message=_message)
        return _message

    @classmethod
    def delete(cls, *, mid: int) -> bool:
        return super().delete(mid=mid)

    @classmethod
    def get_llm_template_by_conversation_id(
        cls, *, conversation_id: str
    ) -> List[Dict[str, str]]:
        # 先从缓存中获取
        cache_key = MessageCache._get_key(conversation_id)
        cached_data = redis_client.lrange(cache_key, 0, -1)
        if cached_data:
            return [json.loads(h) for h in cached_data]

        # 缓存中没有，从数据库中获取
        message_list = super().get_by_conversation_id_and_limit(
            conversation_id=conversation_id
        )
        if message_list is not None:
            data = MessageCache._messages_to_llm_template(
                conversation_id=conversation_id, messages=message_list
            )
            # 修复：将JSON字符串转换为字典
            return [json.loads(item) for item in data] if data else []
        else:
            return []

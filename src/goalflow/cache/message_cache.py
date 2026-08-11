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
    Message cache class
    """

    config = Config()
    # Database page size
    limit: int = 25
    # Cache queue length
    limit_cache: int = limit * 2 - 1
    # limit = config.MESSAGES_PER_PAGE
    # Cache time (seconds)
    ttl: int = 3600

    @classmethod
    def _get_key(cls, conversation_id: str) -> str:
        """
        Get the message cache key
        """
        return f"{RedisKeyConstants.MESSAGE_PREFIX_BY_CONVERSATION_ID}{conversation_id}"

    def _messages_to_llm_template(
        *, conversation_id: str, messages: List[Message]
    ) -> List[Dict[str, str]]:
        """
        Convert a message list into cache format
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
        Convert a message into cache format
        """
        try:
            if BaseCache.has_key(key=MessageCache._get_key(message.conversation_id)):
                # Key exists, meaning the cache has not expired; add the message to the head of the cache queue
                r_key = MessageCache._get_key(message.conversation_id)

                # Only add to the cache when both answer and query are not None and not empty strings
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
                # Key does not exist, need to refresh the cache
                message_list = MessageDB.get_by_conversation_id_and_limit(
                    conversation_id=message.conversation_id, limit=MessageCache.limit
                )

                MessageCache._messages_to_llm_template(
                    conversation_id=message.conversation_id, messages=message_list
                )
                # Convert to cache format
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
        # First get it from the cache
        cache_key = MessageCache._get_key(conversation_id)
        cached_data = redis_client.lrange(cache_key, 0, -1)
        if cached_data:
            return [json.loads(h) for h in cached_data]

        # Not in the cache, get it from the database
        message_list = super().get_by_conversation_id_and_limit(
            conversation_id=conversation_id
        )
        if message_list is not None:
            data = MessageCache._messages_to_llm_template(
                conversation_id=conversation_id, messages=message_list
            )
            # Fix: convert the JSON strings into dicts
            return [json.loads(item) for item in data] if data else []
        else:
            return []

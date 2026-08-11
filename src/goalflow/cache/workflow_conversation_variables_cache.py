import json
import time
from typing import Dict, Any, Optional

from goalflow.infra.base_cache import BaseCache
from goalflow.constants import RedisKeyConstants
from goalflow.infra.database import Config
from goalflow.model.wf_conv_variable import (
    WorkflowConversationVariables,
    WorkflowConversationVariablesDB,
)
from goalflow.infra.redis_manager import redis_client
from goalflow.config import get_logger

logger = get_logger(__name__)


class WorkflowConversationVariablesCache(WorkflowConversationVariablesDB, BaseCache):
    """
    Workflow conversation variables cache class
    """

    config = Config()
    # Cache time (seconds)
    ttl = config.CACHE_DEFAULT_TIMEOUT

    @classmethod
    def create(
        cls, variables: WorkflowConversationVariables
    ) -> WorkflowConversationVariables:
        """
        Create workflow conversation variables (write to the database first, then update the cache)
        """
        start = time.time()

        # Call the parent class method to write to the database
        result = super().create(variables)

        # Update the cache
        if result and result.data:
            cls._set_cache(result.conversation_id, result.data)

        logger.info(
            f"WorkflowConversationVariablesCache create time: {time.time() - start}"
        )
        return result

    @classmethod
    def update(
        cls, *, obj: WorkflowConversationVariables
    ) -> Optional[WorkflowConversationVariables]:
        """
        Update workflow conversation variables (write to the database first, then update the cache)
        """
        # Call the parent class method to update the database
        result = super().update(obj=obj)

        # Update the cache
        if result:
            cls._set_cache(conversation_id=obj.conversation_id, data=obj.data)

        return result

    @classmethod
    def update_by_conversation_id(
        cls, *, conv_vars: WorkflowConversationVariables
    ) -> Optional[WorkflowConversationVariables]:
        """
        Update workflow conversation variables (write to the database first, then update the cache)
        """
        # Call the parent class method to update the database
        result = super().update_by_conversation_id(conv_vars=conv_vars)

        # Update the cache
        if result:
            cls._set_cache(
                conversation_id=conv_vars.conversation_id, data=conv_vars.data
            )

        return result

    @classmethod
    def delete(cls, *, conversation_id: str) -> bool:
        """
        Delete workflow conversation variables (delete from the database first, then delete the cache)
        """
        # Call the parent class method to delete the database record
        result = super().delete(conversation_id=conversation_id)

        # Delete the cache
        if result:
            cls._delete_cache(conversation_id)

        return result

    @classmethod
    def get_by_conversation_id(
        cls, *, conversation_id: str
    ) -> Optional[WorkflowConversationVariables]:
        """
        Query workflow conversation variables by conversation ID (check the cache first, then the database)
        """
        # First get it from the cache
        # cached_data = cls._get_cache(conversation_id)
        try:
            cache_key = cls._get_key(conversation_id)
            cached_data = redis_client.get(cache_key)

            if cached_data is not None:
                # Cache hit, construct the object and return it
                variables = WorkflowConversationVariables(
                    conversation_id=conversation_id, data=cached_data
                )
                return variables

            # Cache miss, query the database
            result = super().get_by_conversation_id(conversation_id=conversation_id)

            # If the database has data, update the cache
            if result and result.data:
                cls._set_cache(conversation_id, result.data)

            return result
        except Exception as e:
            logger.error(f"get_by_conversation_id设置缓存失败: {e}")

    @classmethod
    def get_by_id(cls, *, vid: int) -> Optional[WorkflowConversationVariables]:
        """
        Query workflow conversation variables by ID (query the database directly, since the cache is indexed by conversation_id)
        """
        return super().get_by_id(vid=vid)

    @classmethod
    def _get_key(cls, conversation_id: str) -> str:
        """
        Get the workflow conversation variables cache key
        """
        return (
            f"{RedisKeyConstants.WORKFLOW_PREFIX_BY_CONVERSATION_ID}{conversation_id}"
        )

    @classmethod
    def _set_cache(cls, conversation_id: str, data: Dict[str, Any]) -> None:
        """
        Set the cache
        """
        try:
            cache_key = cls._get_key(conversation_id)
            redis_client.set(cache_key, json.dumps(data, ensure_ascii=False), cls.ttl)
        except Exception as e:
            logger.error(f"_set_cache设置缓存失败: {e}")

    @classmethod
    def _delete_cache(cls, conversation_id: str) -> None:
        """
        Delete the cache
        """
        try:
            cache_key = cls._get_key(conversation_id)
            redis_client.delete(cache_key)
        except Exception as e:
            logger.error(f"删除缓存失败: {e}")

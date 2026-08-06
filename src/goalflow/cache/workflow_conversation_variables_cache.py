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
    工作流会话变量缓存类
    """

    config = Config()
    # 缓存时间（秒）
    ttl = config.CACHE_DEFAULT_TIMEOUT

    @classmethod
    def create(
        cls, variables: WorkflowConversationVariables
    ) -> WorkflowConversationVariables:
        """
        创建工作流会话变量（先写数据库，再更新缓存）
        """
        start = time.time()

        # 调用父类方法写入数据库
        result = super().create(variables)

        # 更新缓存
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
        更新工作流会话变量（先写数据库，再更新缓存）
        """
        # 调用父类方法更新数据库
        result = super().update(obj=obj)

        # 更新缓存
        if result:
            cls._set_cache(conversation_id=obj.conversation_id, data=obj.data)

        return result

    @classmethod
    def update_by_conversation_id(
        cls, *, conv_vars: WorkflowConversationVariables
    ) -> Optional[WorkflowConversationVariables]:
        """
        更新工作流会话变量（先写数据库，再更新缓存）
        """
        # 调用父类方法更新数据库
        result = super().update_by_conversation_id(conv_vars=conv_vars)

        # 更新缓存
        if result:
            cls._set_cache(
                conversation_id=conv_vars.conversation_id, data=conv_vars.data
            )

        return result

    @classmethod
    def delete(cls, *, conversation_id: str) -> bool:
        """
        删除工作流会话变量（先删数据库，再删缓存）
        """
        # 调用父类方法删除数据库记录
        result = super().delete(conversation_id=conversation_id)

        # 删除缓存
        if result:
            cls._delete_cache(conversation_id)

        return result

    @classmethod
    def get_by_conversation_id(
        cls, *, conversation_id: str
    ) -> Optional[WorkflowConversationVariables]:
        """
        根据会话ID查询工作流会话变量（先查缓存，再查数据库）
        """
        # 先从缓存获取
        # cached_data = cls._get_cache(conversation_id)
        try:
            cache_key = cls._get_key(conversation_id)
            cached_data = redis_client.get(cache_key)

            if cached_data is not None:
                # 缓存命中，构造对象返回
                variables = WorkflowConversationVariables(
                    conversation_id=conversation_id, data=cached_data
                )
                return variables

            # 缓存未命中，从数据库查询
            result = super().get_by_conversation_id(conversation_id=conversation_id)

            # 如果数据库有数据，更新缓存
            if result and result.data:
                cls._set_cache(conversation_id, result.data)

            return result
        except Exception as e:
            logger.error(f"get_by_conversation_id设置缓存失败: {e}")

    @classmethod
    def get_by_id(cls, *, vid: int) -> Optional[WorkflowConversationVariables]:
        """
        根据ID查询工作流会话变量（直接查数据库，因为缓存是按conversation_id索引的）
        """
        return super().get_by_id(vid=vid)

    @classmethod
    def _get_key(cls, conversation_id: str) -> str:
        """
        获取工作流会话变量缓存键
        """
        return (
            f"{RedisKeyConstants.WORKFLOW_PREFIX_BY_CONVERSATION_ID}{conversation_id}"
        )

    @classmethod
    def _set_cache(cls, conversation_id: str, data: Dict[str, Any]) -> None:
        """
        设置缓存
        """
        try:
            cache_key = cls._get_key(conversation_id)
            redis_client.set(cache_key, json.dumps(data, ensure_ascii=False), cls.ttl)
        except Exception as e:
            logger.error(f"_set_cache设置缓存失败: {e}")

    @classmethod
    def _delete_cache(cls, conversation_id: str) -> None:
        """
        删除缓存
        """
        try:
            cache_key = cls._get_key(conversation_id)
            redis_client.delete(cache_key)
        except Exception as e:
            logger.error(f"删除缓存失败: {e}")

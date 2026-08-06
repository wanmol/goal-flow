import time
from typing import Dict, Any, Optional

from goalflow.cache.workflow_conversation_variables_cache import (
    WorkflowConversationVariablesCache,
)
from goalflow.model.wf_conv_variable import WorkflowConversationVariables
from goalflow.config import get_logger

logger = get_logger(__name__)


class WorkflowConversationVariablesService:
    """
    工作流会话变量服务
    """

    @staticmethod
    def create(
        conversation_id: str, data: Dict[str, Any], creator_id: str
    ) -> WorkflowConversationVariables:
        """
        创建工作流会话变量

        Args:
            conversation_id: 会话ID
            data: 变量数据

        Returns:
            WorkflowConversationVariables: 创建的变量对象
        """
        start_time = time.time()

        if not conversation_id:
            raise ValueError("conversation_id不能为空")

        if not creator_id:
            creator_id = ''
        variables = WorkflowConversationVariables(
            conversation_id=conversation_id, data=data or {}, creator_id=creator_id,last_updater_id=creator_id
        )

        result = WorkflowConversationVariablesCache.create(variables)
        logger.info(
            f"WorkflowConversationVariablesService create cost time: {time.time() - start_time}"
        )
        return result

    @staticmethod
    def update(
        obj: WorkflowConversationVariables,
    ) -> Optional[WorkflowConversationVariables]:
        """
        更新工作流会话变量

        Args:
            obj: 工作流会话变量
            包含数据 id conversation_id 和 data


        Returns:
            WorkflowConversationVariables: 更新后的变量对象
        """
        if not obj.id:
            raise ValueError("id不能为空")

        if not obj.conversation_id:
            raise ValueError("conversation_id不能为空")

        return WorkflowConversationVariablesCache.update(obj=obj)

    @staticmethod
    def update_by_conversation_id(
        *, conv_vars: WorkflowConversationVariables
    ) -> Optional[WorkflowConversationVariables]:
        """
        更新工作流会话变量

        Args:
            conv_vars: 工作流会话变量
            包含数据 id conversation_id 和 data


        Returns:
            WorkflowConversationVariables: 更新后的变量对象
        """
        if not conv_vars.conversation_id:
            raise ValueError("conversation_id不能为空")

        return WorkflowConversationVariablesCache.update_by_conversation_id(
            conv_vars=conv_vars
        )

    @staticmethod
    def get_by_conversation_id(
        conversation_id: str,
    ) -> Optional[WorkflowConversationVariables]:
        """
        根据会话ID获取工作流会话变量

        Args:
            conversation_id: 会话ID

        Returns:
            WorkflowConversationVariables: 变量对象，如果不存在则返回None
        """
        if not conversation_id:
            raise ValueError("conversation_id不能为空")

        return WorkflowConversationVariablesCache.get_by_conversation_id(
            conversation_id=conversation_id
        )

    @staticmethod
    def get_by_id(vid: int) -> Optional[WorkflowConversationVariables]:
        """
        根据ID获取工作流会话变量

        Args:
            vid: 变量记录ID

        Returns:
            WorkflowConversationVariables: 变量对象，如果不存在则返回None
        """
        if not vid:
            raise ValueError("vid不能为空")

        return WorkflowConversationVariablesCache.get_by_id(vid=vid)

    @staticmethod
    def delete(conversation_id: str) -> bool:
        """
        删除工作流会话变量

        Args:
            conversation_id: 会话ID

        Returns:
            bool: 删除成功返回True，否则返回False
        """
        if not conversation_id:
            raise ValueError("conversation_id不能为空")

        return WorkflowConversationVariablesCache.delete(
            conversation_id=conversation_id
        )

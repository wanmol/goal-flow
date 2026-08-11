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
    Workflow conversation variables service
    """

    @staticmethod
    def create(
        conversation_id: str, data: Dict[str, Any], creator_id: str
    ) -> WorkflowConversationVariables:
        """
        Create workflow conversation variables

        Args:
            conversation_id: conversation ID
            data: variable data

        Returns:
            WorkflowConversationVariables: the created variable object
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
        Update workflow conversation variables

        Args:
            obj: workflow conversation variables
            contains data: id, conversation_id and data


        Returns:
            WorkflowConversationVariables: the updated variable object
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
        Update workflow conversation variables

        Args:
            conv_vars: workflow conversation variables
            contains data: id, conversation_id and data


        Returns:
            WorkflowConversationVariables: the updated variable object
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
        Get workflow conversation variables by conversation ID

        Args:
            conversation_id: conversation ID

        Returns:
            WorkflowConversationVariables: the variable object, or None if it does not exist
        """
        if not conversation_id:
            raise ValueError("conversation_id不能为空")

        return WorkflowConversationVariablesCache.get_by_conversation_id(
            conversation_id=conversation_id
        )

    @staticmethod
    def get_by_id(vid: int) -> Optional[WorkflowConversationVariables]:
        """
        Get workflow conversation variables by ID

        Args:
            vid: variable record ID

        Returns:
            WorkflowConversationVariables: the variable object, or None if it does not exist
        """
        if not vid:
            raise ValueError("vid不能为空")

        return WorkflowConversationVariablesCache.get_by_id(vid=vid)

    @staticmethod
    def delete(conversation_id: str) -> bool:
        """
        Delete workflow conversation variables

        Args:
            conversation_id: conversation ID

        Returns:
            bool: True if deletion succeeded, otherwise False
        """
        if not conversation_id:
            raise ValueError("conversation_id不能为空")

        return WorkflowConversationVariablesCache.delete(
            conversation_id=conversation_id
        )

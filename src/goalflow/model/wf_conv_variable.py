import time
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import VARCHAR, Column, BigInteger, String, DateTime, JSON, Index
from sqlalchemy.ext.declarative import declarative_base

from goalflow.infra.database import Database

Base = declarative_base()


class WorkflowConversationVariables(Base):
    __tablename__ = "wf_conv_variable"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(String(36), nullable=False, index=True, comment="会话ID")
    data = Column(JSON, nullable=False, comment="变量数据")
    creator_id = Column(VARCHAR(36), default="", nullable=True)
    created_at = Column(
        DateTime, name="create_time", nullable=False, comment="create time"
    )
    last_updater_id = Column(VARCHAR(36), default="", nullable=True)
    updated_at = Column(DateTime, name="last_update_time", nullable=False)

    def __init__(
        self,
        *,
        id: Optional[int] = None,
        conversation_id: str = None,
        data: Optional[Dict] = None,
        creator_id: Optional[str] = None,
        last_updater_id: Optional[str] = None,
    ):
        self.id = id
        self.conversation_id = conversation_id
        self.data = data or {}
        self.creator_id = creator_id
        self.last_updater_id = last_updater_id


class WorkflowConversationVariablesDB:
    """工作流会话变量数据库操作类"""

    @classmethod
    def create(
        cls, variables: WorkflowConversationVariables
    ) -> WorkflowConversationVariables:
        """
        创建工作流会话变量记录
        """
        start = time.time()
        now_input = datetime.now()
        variables.created_at = now_input
        variables.updated_at = now_input

        with Database.get_session() as session:
            # 自动处理  conversation_id重复的情况
            session.add(variables)
            session.commit()
            session.refresh(variables)
            if variables is not None:
                session.expunge(
                    variables
                )  # 将对象从会话中分离，这样在会话外也可以访问属性

        return variables

    @classmethod
    def update(
        cls, *, obj: WorkflowConversationVariables
    ) -> Optional[WorkflowConversationVariables]:
        """
        更新工作流会话变量
        conversation_id: 会话ID
        data: 变量数据
        """
        update_data = {"data": obj.data, "updated_at": datetime.now()}

        with Database.get_session() as session:
            # 更新记录
            updated_count = (
                session.query(WorkflowConversationVariables)
                .filter(WorkflowConversationVariables.id == obj.id)
                .update(update_data, synchronize_session=False)
            )

            session.commit()

        return obj

    @classmethod
    def update_by_conversation_id(
        cls, *, conv_vars: WorkflowConversationVariables
    ) -> Optional[WorkflowConversationVariables]:
        """
        更新工作流会话变量
        conversation_id: 会话ID
        data: 变量数据
        """
        update_data = {
            "data": conv_vars.data,
            "updated_at": datetime.now(),
            "last_updater_id": conv_vars.last_updater_id,
        }

        with Database.get_session() as session:
            # 更新记录
            session.query(WorkflowConversationVariables).filter(
                WorkflowConversationVariables.conversation_id
                == conv_vars.conversation_id
            ).update(update_data, synchronize_session=False)
            session.commit()

        return conv_vars

    @classmethod
    def delete(cls, *, conversation_id: str) -> bool:
        """
        删除工作流会话变量
        conversation_id: 会话ID
        """
        with Database.get_session() as session:
            variables = (
                session.query(WorkflowConversationVariables)
                .filter(
                    WorkflowConversationVariables.conversation_id == conversation_id
                )
                .first()
            )

            if variables is not None:
                session.delete(variables)
                session.commit()
                return True
            return False

    @classmethod
    def get_by_id(cls, *, vid: int) -> Optional[WorkflowConversationVariables]:
        """
        根据ID查询工作流会话变量
        vid: 变量记录ID
        """
        with Database.get_session() as session:
            variables = (
                session.query(WorkflowConversationVariables)
                .filter(WorkflowConversationVariables.id == vid)
                .first()
            )

            if variables is not None:
                session.expunge(variables)
                return variables
            return None

    @classmethod
    def get_by_conversation_id(
        cls, *, conversation_id: str
    ) -> Optional[WorkflowConversationVariables]:
        """
        根据会话ID查询工作流会话变量
        conversation_id: 会话ID
        """
        with Database.get_session() as session:
            variables = (
                session.query(WorkflowConversationVariables)
                .filter(
                    WorkflowConversationVariables.conversation_id == conversation_id
                )
                .first()
            )

            if variables is not None:
                session.expunge(variables)
                return variables
            return None

    @classmethod
    def upsert(
        cls, *, conversation_id: str, data: Dict[str, Any]
    ) -> WorkflowConversationVariables:
        """
        插入或更新工作流会话变量（如果存在则更新，不存在则创建）
        conversation_id: 会话ID
        data: 变量数据
        """
        existing = cls.get_by_conversation_id(conversation_id=conversation_id)

        if existing:
            # 更新现有记录
            return cls.update(conversation_id=conversation_id, data=data)
        else:
            # 创建新记录
            variables = WorkflowConversationVariables(
                conversation_id=conversation_id, data=data
            )
            return cls.create(variables)

    @classmethod
    def merge_data(
        cls, *, conversation_id: str, new_data: Dict[str, Any]
    ) -> Optional[WorkflowConversationVariables]:
        """
        合并变量数据（将新数据合并到现有数据中）
        conversation_id: 会话ID
        new_data: 要合并的新数据
        """
        existing = cls.get_by_conversation_id(conversation_id=conversation_id)

        if existing:
            # 合并数据
            merged_data = existing.data.copy() if existing.data else {}
            merged_data.update(new_data)
            return cls.update(conversation_id=conversation_id, data=merged_data)
        else:
            # 创建新记录
            variables = WorkflowConversationVariables(
                conversation_id=conversation_id, data=new_data
            )
            return cls.create(variables)

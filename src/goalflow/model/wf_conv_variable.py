import time
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import VARCHAR, Column, BigInteger, String, DateTime, JSON, Index
from sqlalchemy.ext.declarative import declarative_base

from goalflow.infra.database import Database

Base = declarative_base()


class WorkflowConversationVariables(Base):
    __tablename__ = "agent_conv_variable"

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
    """Workflow conversation variables database operations class"""

    @classmethod
    def create(
        cls, variables: WorkflowConversationVariables
    ) -> WorkflowConversationVariables:
        """
        Create a workflow conversation variables record
        """
        start = time.time()
        now_input = datetime.now()
        variables.created_at = now_input
        variables.updated_at = now_input

        with Database.get_session() as session:
            # Automatically handle the case of a duplicate conversation_id
            session.add(variables)
            session.commit()
            session.refresh(variables)
            if variables is not None:
                session.expunge(
                    variables
                )  # Detach the object from the session so its attributes can be accessed outside the session

        return variables

    @classmethod
    def update(
        cls, *, obj: WorkflowConversationVariables
    ) -> Optional[WorkflowConversationVariables]:
        """
        Update workflow conversation variables
        conversation_id: conversation ID
        data: variable data
        """
        update_data = {"data": obj.data, "updated_at": datetime.now()}

        with Database.get_session() as session:
            # Update the record
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
        Update workflow conversation variables
        conversation_id: conversation ID
        data: variable data
        """
        update_data = {
            "data": conv_vars.data,
            "updated_at": datetime.now(),
            "last_updater_id": conv_vars.last_updater_id,
        }

        with Database.get_session() as session:
            # Update the record
            session.query(WorkflowConversationVariables).filter(
                WorkflowConversationVariables.conversation_id
                == conv_vars.conversation_id
            ).update(update_data, synchronize_session=False)
            session.commit()

        return conv_vars

    @classmethod
    def delete(cls, *, conversation_id: str) -> bool:
        """
        Delete workflow conversation variables
        conversation_id: conversation ID
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
        Query workflow conversation variables by ID
        vid: variable record ID
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
        Query workflow conversation variables by conversation ID
        conversation_id: conversation ID
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
        Insert or update workflow conversation variables (update if it exists, create if it does not)
        conversation_id: conversation ID
        data: variable data
        """
        existing = cls.get_by_conversation_id(conversation_id=conversation_id)

        if existing:
            # Update the existing record
            return cls.update(conversation_id=conversation_id, data=data)
        else:
            # Create a new record
            variables = WorkflowConversationVariables(
                conversation_id=conversation_id, data=data
            )
            return cls.create(variables)

    @classmethod
    def merge_data(
        cls, *, conversation_id: str, new_data: Dict[str, Any]
    ) -> Optional[WorkflowConversationVariables]:
        """
        Merge variable data (merge new data into the existing data)
        conversation_id: conversation ID
        new_data: the new data to merge
        """
        existing = cls.get_by_conversation_id(conversation_id=conversation_id)

        if existing:
            # Merge the data
            merged_data = existing.data.copy() if existing.data else {}
            merged_data.update(new_data)
            return cls.update(conversation_id=conversation_id, data=merged_data)
        else:
            # Create a new record
            variables = WorkflowConversationVariables(
                conversation_id=conversation_id, data=new_data
            )
            return cls.create(variables)

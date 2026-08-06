import time
from datetime import datetime  # 替换 import datetime
from typing import List
from typing import Optional, Dict

from sqlalchemy import (
    VARCHAR,
    Column,
    BigInteger,
    String,
    Text,
    DateTime,
    func,
    Index,
    JSON,
)
from sqlalchemy.ext.declarative import declarative_base

from goalflow.infra.database import Database
from goalflow.config import get_logger

logger = get_logger(__name__)

Base = declarative_base()


class Message(Base):
    __tablename__ = "wf_message"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(
        String(36), nullable=False, index=True, comment="session id"
    )
    message_id = Column(String(36), nullable=False, default=func.uuid())
    inputs = Column(JSON, nullable=True)
    query = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    scene_type = Column(VARCHAR(50), default="WANMOL", nullable=True)
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
        message_id: Optional[str] = None,
        inputs: Optional[Dict] = None,
        query: Optional[str] = None,
        answer: Optional[str] = None,
        scene_type: Optional[str] = None,
        creator_id: Optional[str] = None,
        last_updater_id: Optional[str] = None,
    ):
        self.id = id
        self.conversation_id = conversation_id
        self.message_id = message_id
        self.inputs = inputs
        self.query = query
        self.answer = answer
        self.scene_type  = scene_type
        self.creator_id = creator_id
        self.last_updater_id = last_updater_id


class MessageDB:

    @classmethod
    def create(cls, message: Message) -> Message:
        """
        对话记录存储到DB
        """

        start = time.time()
        now_input = datetime.now()
        message.created_at = now_input
        message.updated_at = now_input
        with Database.get_session() as session:
            session.add(message)
            session.commit()
            session.refresh(message)
            if message is not None:
                session.expunge(
                    message
                )  # 将对象从会话中分离，这样在会话外也可以访问属性

        logger.info(f"create_message time: {time.time() - start}")

        return message

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
        """
        更新消息
        mid: 消息id
        answer: 答案
        """
        update_data = {
            "answer": answer,
            "updated_at": datetime.now(),
            "last_updater_id": last_updater_id,
        }
        with Database.get_session() as session:
            session.query(Message).filter(Message.id == mid).update(
                update_data, synchronize_session=False
            )
            _message = Message(
                id=mid,
                conversation_id=conversation_id,
                answer=answer,
                query=query,
                last_updater_id=last_updater_id,
            )
            return _message

    @classmethod
    def delete(cls, *, mid: int) -> bool:
        """
        删除消息
        mid: 消息id
        TODO 有删除消息的可能吗 ？？？
        """
        with Database.get_session() as session:
            message = session.query(Message).filter(Message.id == mid).first()
            if message is not None:
                session.delete(message)
                session.commit()
                return True
            return False

    @classmethod
    def get_by_id(cls, *, mid: int) -> Optional[Message]:
        """
        根据id查询消息
        mid: 消息id
        """
        with Database.get_session() as session:
            message = session.query(Message).filter(Message.id == mid).first()

            if message is not None:
                session.expunge(message)
                return message
            return None

    @classmethod
    def get_by_message_id(cls, *, message_id: str) -> Optional[Message]:
        """
        根据message_id查询消息
        message_id: 消息message_id
        """
        with Database.get_session() as session:
            message = (
                session.query(Message).filter(Message.message_id == message_id).first()
            )
            if message is not None:
                session.expunge(message)
                return message
        return None

    @classmethod
    def get_by_conversation_id_and_limit(
        cls, *, conversation_id: str, limit: int = 25
    ) -> List[Message]:
        """
        根据会话id，分页条件查询数据,默认查询20条数据
        conversation_id: 会话id
        limit: 分页大小，默认25条
        """
        if not conversation_id:
            raise ValueError("conversation_id不能为空")
        with Database.get_session() as session:
            messages = (
                session.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
                .all()
            )
            for message in messages:
                session.expunge(message)
        return messages

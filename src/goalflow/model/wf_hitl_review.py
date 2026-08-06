"""
HITL Review 数据库模型和操作类
用于存储 HITL 审核记录
"""

from datetime import datetime
from typing import Optional, Dict, List

from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Text,
    DateTime,
    JSON,
    Index,
    VARCHAR,
)
from sqlalchemy.ext.declarative import declarative_base

from goalflow.infra.database import Database
from goalflow.config import get_logger

logger = get_logger(__name__)

Base = declarative_base()


class HITLReview(Base):
    """HITL 审核记录表"""

    __tablename__ = "wf_hitl_review"

    # 主键
    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # 审核标识
    review_id = Column(
        String(128), nullable=False, unique=True, index=True, comment="审核ID"
    )
    workflow_id = Column(String(128), nullable=False, index=True, comment="工作流ID")
    workflow_run_id = Column(
        String(128), nullable=False, index=True, comment="工作流运行ID"
    )
    checkpoint_name = Column(String(64), nullable=False, comment="checkpoint名称")

    thread_id = Column(String(100), nullable=False, comment="thread_id")
    
    interrupt_id = Column(String(50), nullable=False, comment="中断ID")

    # 审核状态
    status = Column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
        comment="状态: pending/approved/modified/rejected",
    )

    # 审核数据
    data = Column(JSON, nullable=False, comment="待审核数据（研究框架等）")
    modified_data = Column(JSON, nullable=True, comment="修改后的数据")

    # 审核信息
    action = Column(
        String(32), nullable=True, comment="审核动作: approve/modify/reject"
    )

    submitted_by = Column(VARCHAR(36), nullable=True, comment="审核人ID")

    # 时间管理
    created_at = Column(DateTime, nullable=False, comment="创建时间")
    expires_at = Column(DateTime, nullable=False, comment="过期时间")
    submitted_at = Column(DateTime, nullable=True, comment="提交时间")
    updated_at = Column(DateTime, nullable=False, comment="更新时间")

    # 索引
    __table_args__ = (
        Index("idx_workflow_id", "workflow_id"),
        Index("idx_workflow_run_id", "workflow_run_id"),
        Index("idx_status", "status"),
        Index("idx_created_at", "created_at"),
    )

    def __init__(
        self,
        *,
        id: Optional[int] = None,
        review_id: str,
        workflow_id: str,
        workflow_run_id: str,
        checkpoint_name: str,
        thread_id: str,
        status: str = "pending",
        data: Dict,
        modified_data: Optional[Dict] = None,
        action: Optional[str] = None,
        submitted_by: Optional[str] = None,
        expires_at: datetime,
    ):
        self.id = id
        self.review_id = review_id
        self.workflow_id = workflow_id
        self.workflow_run_id = workflow_run_id
        self.checkpoint_name = checkpoint_name
        self.thread_id = thread_id
        self.status = status
        self.data = data
        self.modified_data = modified_data
        self.action = action
        self.submitted_by = submitted_by
        self.expires_at = expires_at


class HITLReviewDB:
    """HITL 审核数据库操作类"""

    @classmethod
    def create(cls, review: HITLReview) -> HITLReview:
        """
        创建审核记录

        Args:
            review: HITLReview 对象

        Returns:
            HITLReview: 创建后的对象（包含 ID）
        """
        now = datetime.now()
        review.created_at = now
        review.updated_at = now

        with Database.get_session() as session:
            session.add(review)
            session.commit()
            session.refresh(review)
            if review is not None:
                session.expunge(review)

        logger.info(f"Created HITL review: {review.review_id}")
        return review

    @classmethod
    def get_by_review_id(cls, review_id: str) -> Optional[HITLReview]:
        """
        根据 review_id 查询审核记录

        Args:
            review_id: 审核ID

        Returns:
            Optional[HITLReview]: 审核记录或 None
        """
        with Database.get_session() as session:
            review = (
                session.query(HITLReview)
                .filter(HITLReview.review_id == review_id)
                .first()
            )

            if review:
                session.expunge(review)
                return review
            return None

    @classmethod
    def get_pending_by_workflow_run_id(cls, workflow_run_id: str) -> List[HITLReview]:
        """
        获取工作流的待审核记录

        Args:
            workflow_run_id: 工作流运行ID

        Returns:
            List[HITLReview]: 待审核记录列表
        """
        with Database.get_session() as session:
            reviews = (
                session.query(HITLReview)
                .filter(
                    HITLReview.workflow_run_id == workflow_run_id,
                    HITLReview.status == "pending",
                )
                .order_by(HITLReview.created_at.desc())
                .all()
            )

            for review in reviews:
                session.expunge(review)

            return reviews

    @classmethod
    def get_all_by_workflow_run_id(cls, workflow_run_id: str) -> List[HITLReview]:
        """
        获取工作流的所有审核记录（包括已完成的）

        Args:
            workflow_run_id: 工作流运行ID

        Returns:
            List[HITLReview]: 审核记录列表
        """
        with Database.get_session() as session:
            reviews = (
                session.query(HITLReview)
                .filter(HITLReview.workflow_run_id == workflow_run_id)
                .order_by(HITLReview.created_at.desc())
                .all()
            )

            for review in reviews:
                session.expunge(review)

            return reviews

    @classmethod
    def update_status(
        cls,
        review_id: str,
        status: str,
        action: Optional[str] = None,
        modified_data: Optional[Dict] = None,
        submitted_by: Optional[str] = None,
    ) -> bool:
        """
        更新审核状态

        Args:
            review_id: 审核ID
            status: 新状态
            action: 审核动作
            modified_data: 修改后的数据
            submitted_by: 审核人ID

        Returns:
            bool: 是否更新成功
        """
        with Database.get_session() as session:
            update_data = {"status": status, "updated_at": datetime.now()}

            if action:
                update_data["action"] = action
            if modified_data is not None:
                update_data["modified_data"] = modified_data
            if submitted_by:
                update_data["submitted_by"] = submitted_by

            # 如果是最终状态，记录提交时间
            if status in ["approved", "modified", "rejected"]:
                update_data["submitted_at"] = datetime.now()

            rows_updated = (
                session.query(HITLReview)
                .filter(HITLReview.review_id == review_id)
                .update(update_data, synchronize_session=False)
            )

            if rows_updated > 0:
                logger.info(f"Updated HITL review {review_id} to status: {status}")
                return True
            else:
                logger.warning(f"HITL review {review_id} not found")
                return False

    @classmethod
    def cleanup_expired(cls) -> int:
        """
        清理过期的 pending 记录

        Returns:
            int: 清理的记录数量
        """
        with Database.get_session() as session:
            count = (
                session.query(HITLReview)
                .filter(
                    HITLReview.status == "pending",
                    HITLReview.expires_at < datetime.now(),
                )
                .delete(synchronize_session=False)
            )

            if count > 0:
                logger.info(f"Cleaned up {count} expired HITL reviews")

            return count

    @classmethod
    def get_by_id(cls, id: int) -> Optional[HITLReview]:
        """
        根据 ID 查询审核记录

        Args:
            id: 记录ID

        Returns:
            Optional[HITLReview]: 审核记录或 None
        """
        with Database.get_session() as session:
            review = session.query(HITLReview).filter(HITLReview.id == id).first()

            if review:
                session.expunge(review)
                return review
            return None
        
    @classmethod
    def update_interrupt_id(
        cls,
        review_id: str,
        interrupt_id: Optional[str] = None,
    ) -> bool:
        """更新中断ID"""
        with Database.get_session() as session:
            update_fields = {"interrupt_id": interrupt_id}

            rows = (
                session.query(HITLReview)
                .filter(HITLReview.review_id == review_id)
                .update(update_fields, synchronize_session=False)
            )
            session.commit()

        if rows > 0:
            logger.info(f"HITLReview updated: review_id={review_id} interrupt_id={interrupt_id}")
            return True
        logger.warning(f"HITLReview not found: review_id={review_id}")
        return False

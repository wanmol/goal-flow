"""
HITL Review database model and operations class
Used to store HITL review records
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
    """HITL review record table"""

    __tablename__ = "wf_hitl_review"

    # Primary key
    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Review identifiers
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

    # Review status
    status = Column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
        comment="状态: pending/approved/modified/rejected",
    )

    # Review data
    data = Column(JSON, nullable=False, comment="待审核数据（研究框架等）")
    modified_data = Column(JSON, nullable=True, comment="修改后的数据")

    # Review information
    action = Column(
        String(32), nullable=True, comment="审核动作: approve/modify/reject"
    )

    submitted_by = Column(VARCHAR(36), nullable=True, comment="审核人ID")

    # Time management
    created_at = Column(DateTime, nullable=False, comment="创建时间")
    expires_at = Column(DateTime, nullable=False, comment="过期时间")
    submitted_at = Column(DateTime, nullable=True, comment="提交时间")
    updated_at = Column(DateTime, nullable=False, comment="更新时间")

    # Indexes
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
    """HITL review database operations class"""

    @classmethod
    def create(cls, review: HITLReview) -> HITLReview:
        """
        Create a review record

        Args:
            review: HITLReview object

        Returns:
            HITLReview: the created object (including ID)
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
        Query a review record by review_id

        Args:
            review_id: review ID

        Returns:
            Optional[HITLReview]: the review record or None
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
        Get the pending review records of a workflow

        Args:
            workflow_run_id: workflow run ID

        Returns:
            List[HITLReview]: list of pending review records
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
        Get all review records of a workflow (including completed ones)

        Args:
            workflow_run_id: workflow run ID

        Returns:
            List[HITLReview]: list of review records
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
        Update the review status

        Args:
            review_id: review ID
            status: new status
            action: review action
            modified_data: modified data
            submitted_by: reviewer ID

        Returns:
            bool: whether the update succeeded
        """
        with Database.get_session() as session:
            update_data = {"status": status, "updated_at": datetime.now()}

            if action:
                update_data["action"] = action
            if modified_data is not None:
                update_data["modified_data"] = modified_data
            if submitted_by:
                update_data["submitted_by"] = submitted_by

            # If it is a final status, record the submission time
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
        Clean up expired pending records

        Returns:
            int: the number of records cleaned up
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
        Query a review record by ID

        Args:
            id: record ID

        Returns:
            Optional[HITLReview]: the review record or None
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
        """Update the interrupt ID"""
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

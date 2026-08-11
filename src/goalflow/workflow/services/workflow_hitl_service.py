"""
HITL workflow controller
Manages the pause, resume and status query of the HITL review process
"""

from typing import Optional, Dict, List, Any
from datetime import datetime
from goalflow.model import HITLReview, HITLReviewDB
from goalflow.config import get_logger
from goalflow.workflow.base_workflow import BaseWorkflow
from goalflow.state import GenericState, BaseState
from goalflow.api.base_types import format_stream_chunk
from goalflow.workflow.services.chatflow_generate_service import ChatflowGenerateService
from langgraph.types import Interrupt


logger = get_logger(__name__)


class WorkflowHitlService:
    """HITL(human in the loop) workflow controller"""
    def __init__(self, workflow: BaseWorkflow[GenericState]):
        self.workflow = workflow

    def get_pending_reviews(self, workflow_run_id: str) -> List[Dict[str, Any]]:
        """
        Get the pending review records of the workflow

        Args:
            workflow_run_id: workflow run ID

        Returns:
            List[Dict]: list of pending review records (converted to dicts)
        """
        reviews = HITLReviewDB.get_pending_by_workflow_run_id(workflow_run_id)
        
        return [self._review_to_dict(review) for review in reviews]
    
    def get_review(self, review_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single review record

        Args:
            review_id: review ID

        Returns:
            Optional[Dict]: review record (converted to dict) or None
        """
        review = HITLReviewDB.get_by_review_id(review_id)
        
        if review:
            return self._review_to_dict(review)
        return None
    
    def get_all_reviews(self, workflow_run_id: str) -> List[Dict[str, Any]]:
        """
        Get all review records of the workflow

        Args:
            workflow_run_id: workflow run ID

        Returns:
            List[Dict]: list of all review records
        """
        reviews = HITLReviewDB.get_all_by_workflow_run_id(workflow_run_id)
        
        return [self._review_to_dict(review) for review in reviews]
    
    
    
    def submit_review(
        self,
        *, 
        review_id: str,
        action: str,
        modified_data: Optional[Dict] = None,
        submitted_by: Optional[str] = None,
        init_state: Dict[str, Any] = {}
    ) :
        """
        Submit review result

        Args:
            review_id: review ID
            action: review action (approve/modify/reject)
            modified_data: modified data (only when action=modify)
            submitted_by: reviewer ID

        Returns:
            bool: whether the submission was successful
        """
        workflow_run_id = init_state.get("sys_workflow_run_id")
        # validate action
        if action not in ['approve', 'modify', 'reject']:
            logger.error(f"Invalid action: {action}")
            yield format_stream_chunk(
                # chunck_id has no actual business need for now, the frontend does not use it either, assign a temporary value
                chunk_id=action,
                event_type="error",
                data={
                    "error_type": "invalid_action",
                    "workflow_run_id": workflow_run_id,
                },
                message=f"invalid_action: {action}",
                task_id=workflow_run_id,
            )
        
        # if it is modify, modified_data must be provided
        if action == 'modify' and not modified_data:
            logger.error("Modified data is required for 'modify' action")
            yield format_stream_chunk(
                # chunck_id has no actual business need for now, the frontend does not use it either, assign a temporary value
                chunk_id=action,
                event_type="error",
                data={
                    "error_type": "missing_modified_data`",
                    "workflow_run_id": workflow_run_id,
                },
                message="modified_data is required for 'modify' action",
                task_id=workflow_run_id,
            )
        
        # update review status
        success = HITLReviewDB.update_status(
            review_id=review_id,
            status=action,  # approve/modify/reject
            action=action,
            modified_data=modified_data,
            submitted_by=submitted_by
        )
        
        if success:
            logger.info(
                f"Review {review_id} submitted with action: {action}"
            )

        # get review record
        review = HITLReviewDB.get_by_review_id(review_id)
        if not review:
            logger.error(f"Review {review_id} not found after update")
            yield format_stream_chunk(
                chunk_id=action,
                event_type="error",
                data={
                    "error_type": "review_not_found",
                    "workflow_run_id": workflow_run_id,
                },
                message=f"Review {review_id} not found",
                task_id=workflow_run_id,
            )
            return
        
        thread_id = review.thread_id
        if not thread_id:
            logger.error(f"Review {review_id} has no thread_id")
            yield format_stream_chunk(
                chunk_id=action,
                event_type="error",
                data={
                    "error_type": "missing_thread_id",
                    "workflow_run_id": workflow_run_id,
                },
                message=f"Review {review_id} has no thread_id",
                task_id=workflow_run_id,
            )
            return
        
        # get the original framework data
        # ✅ handle the nested structure of modified_data: {"research_framework": {...}}
        if modified_data and isinstance(modified_data, dict) and modified_data:  # ensure non-empty dict
            # if modified_data contains the research_framework field, extract it
            if "research_framework" in modified_data:
                research_framework = modified_data.get("research_framework")
                # ✅ if the extracted value is empty, use the original framework
                if not research_framework:
                    research_framework = review.data.get("research_framework") if review.data else None
            else:
                # otherwise assume modified_data itself is the research_framework
                research_framework = modified_data
        else:
            # if no modified data is provided or it is empty, use the original data
            research_framework = review.data.get("research_framework") if review.data else None

        # restore the required context fields from review.data
        review_data = review.data if review.data else {}

        chat_service:ChatflowGenerateService = ChatflowGenerateService(self.workflow)

        # the subsequent nodes of the resume operation may have interruption points
        chat_service.bind_interrupt_hook(self)

        # construct the resume state (containing all required fields)
        state_param = {
            "hitl_review_id" : review_id,
            "interrupt_id": review.interrupt_id,
            "research_framework": research_framework,
            "hitl_action" : action,
            # restore the state before the breakpoint via checkpoint
            "rt_thread_id" : thread_id,
            # context fields restored from review.data
            "sys_user_id": review_data.get("sys_user_id"),
            "sys_conversation_id": review_data.get("sys_conversation_id"),
            "sys_query": review_data.get("sys_query"),
            "input_variables": review_data.get("input_variables", {}),
            # ✅ restore time parameters (if present)
            "sys_current_date": review_data.get("sys_current_date"),
            "sys_current_datetime": review_data.get("sys_current_datetime"),
        }

        # values in init_state have higher priority (only update non-empty fields)
        for key, value in init_state.items():
            if value is not None:  # only update fields that have a value
                state_param[key] = value

        try:
            response = chat_service.generate(
               state_param
            )
            
            # stream the results back
            yield from response
        except Exception as e:
            logger.error(f"Failed to resume workflow: {e}", exc_info=True)
            yield format_stream_chunk(
                chunk_id=action,
                event_type="error",
                data={
                    "error_type": "workflow_resume_failed",
                    "workflow_run_id": workflow_run_id,
                },
                message=f"Failed to resume workflow: {str(e)}",
                task_id=workflow_run_id,
            )
    
    def approve(
        self,
        *,
        review_id: str,
        submitted_by: Optional[str] = None,
        init_state: Dict[str, Any]
    ) :
        """
        Approve review (shortcut method)

        Args:
            review_id: review ID
            submitted_by: reviewer ID

        Returns:
            bool: whether the approval was successful
        """
        return self.submit_review(
            review_id=review_id,
            action='approve',
            submitted_by=submitted_by,
            init_state=init_state,
        )
    
    def modify(
        self,
        review_id: str,
        modified_data: Dict,
        submitted_by: Optional[str] = None,
        init_state: Dict[str, Any] = {}
    ) -> bool:
        """
        Approve after modification (shortcut method)

        Args:
            review_id: review ID
            modified_data: modified data
            submitted_by: reviewer ID

        Returns:
            bool: whether the modification was successful
        """
        return self.submit_review(
            review_id=review_id,
            action='modify',
            modified_data=modified_data,
            submitted_by=submitted_by,
            init_state=init_state,
        )
    
    def reject(
        self,
        review_id: str,
        submitted_by: Optional[str] = None,
        init_state: Dict[str, Any] = {}
    ) -> bool:
        """
        Reject review (shortcut method)

        Args:
            review_id: review ID
            submitted_by: reviewer ID

        Returns:
            bool: whether the rejection was successful
        """
        return self.submit_review(
            review_id=review_id,
            action='reject',
            submitted_by=submitted_by,
            init_state=init_state,
        )
    
    def cleanup_expired_reviews(self) -> int:
        """
        Clean up expired pending review records

        Returns:
            int: number of cleaned records
        """
        count = HITLReviewDB.cleanup_expired()
        logger.info(f"Cleaned up {count} expired reviews")
        return count
    

    def get_workflow_status(self, workflow_run_id: str) -> Dict[str, Any]:
        """
        Get the HITL status of the workflow

        Args:
            workflow_run_id: workflow run ID

        Returns:
            Dict: workflow HITL status information
        """
        pending_reviews = self.get_pending_reviews(workflow_run_id)
        all_reviews = self.get_all_reviews(workflow_run_id)
        
        status = {
            "workflow_run_id": workflow_run_id,
            "has_pending_reviews": len(pending_reviews) > 0,
            "pending_count": len(pending_reviews),
            "total_reviews": len(all_reviews),
            "pending_reviews": pending_reviews,
            "status": "paused_for_review" if pending_reviews else "no_pending_reviews"
        }
        
        return status
    

    def _review_to_dict(self,review: HITLReview) -> Dict[str, Any]:
        """
        Convert a Review object to a dict

        Args:
            review: HITLReview object

        Returns:
            Dict: review record dict
        """
        return {
            "id": review.id,
            "review_id": review.review_id,
            "workflow_id": review.workflow_id,
            "workflow_run_id": review.workflow_run_id,
            "checkpoint_name": review.checkpoint_name,
            "status": review.status,
            "data": review.data,
            "modified_data": review.modified_data,
            "action": review.action,
            "submitted_by": review.submitted_by,
            "created_at": review.created_at.isoformat() if review.created_at else None,
            "expires_at": review.expires_at.isoformat() if review.expires_at else None,
            "submitted_at": review.submitted_at.isoformat() if review.submitted_at else None,
            "updated_at": review.updated_at.isoformat() if review.updated_at else None,
        }
        
    #TODO the interrupt_id field of table aira_wf_hitl_review needs to be updated
    def after_interrupt(self, interrupt: Interrupt) -> object:
        review_id = interrupt.value["review_id"]
        interrupt_id = interrupt.id
        
        logger.info(f"after_interrupt: review_id={review_id}, interrupt_id={interrupt_id}")
        
        HITLReviewDB.update_interrupt_id(review_id, interrupt_id)


# convenience functions
def get_pending_reviews(workflow:BaseWorkflow,workflow_run_id: str) -> List[Dict[str, Any]]:
    """Get pending review records (convenience function)"""
    return WorkflowHitlService(workflow).get_pending_reviews(workflow_run_id)


def submit_feedback(
    workflow:BaseWorkflow,
    review_id: str,
    action: str,
    modified_data: Optional[Dict] = None,
    submitted_by: Optional[str] = None,
    init_state: Dict[str, Any] = {}
) -> bool:
    """Submit review result (convenience function, deprecated)"""
    return WorkflowHitlService(workflow).submit_review(
        review_id=review_id,
        action=action,
        modified_data=modified_data,
        submitted_by=submitted_by,
        init_state=init_state
    )


def approve_workflow(
    workflow:BaseWorkflow,
    review_id: str,
    submitted_by: Optional[str] = None,
    init_state: Dict[str, Any] = {}
) -> bool:
    """Approve review (convenience function, deprecated)"""
    return WorkflowHitlService(workflow).approve(
        review_id=review_id,
        submitted_by=submitted_by,
        init_state=init_state
    )


def approve_with_modification(
    workflow:BaseWorkflow,
    review_id: str,
    modified_data: Dict,
    submitted_by: Optional[str] = None,
    init_state: Dict[str, Any] = {}
) -> bool:
    """Approve after modification (convenience function, deprecated)"""
    return WorkflowHitlService(workflow).modify(
        review_id=review_id,
        modified_data=modified_data,
        submitted_by=submitted_by,
        init_state=init_state
    )


def reject_workflow(
    workflow:BaseWorkflow,
    review_id: str,
    submitted_by: Optional[str] = None,
    init_state: Dict[str, Any] = {}
) -> bool:
    """Reject review (convenience function, deprecated)"""
    return WorkflowHitlService(workflow).reject(
        review_id=review_id,
        submitted_by=submitted_by,
        init_state=init_state
    )


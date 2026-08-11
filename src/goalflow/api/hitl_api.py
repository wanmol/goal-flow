"""
HITL (Human-in-the-Loop) API interface
Provides an HTTP REST API for external systems to submit reviews and resume workflows
"""

from fastapi import APIRouter, HTTPException, status,Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

from goalflow.api.auth_validator import validate_token_and_get_wf

from goalflow.workflow.base_workflow import BaseWorkflow

from goalflow.config import request_id as request_id_ctx
from goalflow.constants import (
    WF_REQUEST_ID_HEADER_NAME
)

#from workflow.hitl_controller import HITLWorkflowController
from goalflow.workflow.services.workflow_hitl_service import WorkflowHitlService

import json

from goalflow.config import get_logger

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/hitl", tags=["HITL"])


# ==================== Pydantic Models ====================

class ApproveInputs(BaseModel):
    """Approve review input parameters"""
    review_id: str = Field(..., description="审核ID")
    submitted_by: Optional[str] = Field(None, description="审核人ID")


class ApproveRequest(BaseModel):
    """Approve review request"""
    inputs: ApproveInputs = Field(..., description="输入参数")


class ModifyInputs(BaseModel):
    """Approve-after-modification input parameters"""
    review_id: str = Field(..., description="审核ID")
    modified_data: Dict[str, Any] = Field(..., description="修改后的数据")
    submitted_by: Optional[str] = Field(None, description="审核人ID")


class ModifyRequest(BaseModel):
    """Approve-after-modification request"""
    inputs: ModifyInputs = Field(..., description="输入参数")


class RejectInputs(BaseModel):
    """Reject review input parameters"""
    review_id: str = Field(..., description="审核ID")
    submitted_by: Optional[str] = Field(None, description="审核人ID")


class RejectRequest(BaseModel):
    """Reject review request"""
    inputs: RejectInputs = Field(..., description="输入参数")


class ResumeInputs(BaseModel):
    """Resume workflow input parameters"""
    review_id: str = Field(..., description="审核ID")


class ResumeRequest(BaseModel):
    """Resume workflow request"""
    inputs: ResumeInputs = Field(..., description="输入参数")


class ReviewResponse(BaseModel):
    """Review response"""
    status: str
    message: str
    review_id: str
    workflow_run_id: Optional[str] = None

class StreamReviewChunk(BaseModel):
    """Streaming review data chunk"""
    review_id: str
    #status: str
    data: Dict[str, Any]
    workflow_run_id: Optional[str] = None


# ==================== API Endpoints ====================

@router.get("/reviews/{review_id}", summary="查询审核详情")
def get_review(
        review_id: str,
        workflow: BaseWorkflow = Depends(validate_token_and_get_wf)
    ) -> Dict[str, Any]:
    """
    Query review details

    Args:
        review_id: review ID

    Returns:
        review details
    """
    try:
        review = WorkflowHitlService(workflow).get_review(review_id)
        
        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Review {review_id} not found"
            )
        
        return review
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get review {review_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get review: {str(e)}"
        )


@router.get("/workflows/{workflow_run_id}/reviews", summary="查询工作流的所有审核")
def get_workflow_reviews(
        workflow_run_id: str,
        workflow: BaseWorkflow = Depends(validate_token_and_get_wf)
    ) -> Dict[str, Any]:
    """
    Query all reviews of a workflow

    Args:
        workflow_run_id: workflow run ID

    Returns:
        review list
    """
    try:
        reviews = WorkflowHitlService(workflow).get_all_reviews(workflow_run_id)
        
        return {
            "workflow_run_id": workflow_run_id,
            "total": len(reviews),
            "reviews": reviews
        }
        
    except Exception as e:
        logger.error(f"Failed to get reviews for workflow {workflow_run_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get reviews: {str(e)}"
        )


@router.post("/reviews/approve", summary="批准审核")
def approve_review(
    request: Request,
    request_body: ApproveRequest,
    workflow: BaseWorkflow = Depends(validate_token_and_get_wf)
) :
    """
    Approve review

    Args:
        request: HTTP request
        request_body: approve request body (contains review_id)

    Returns:
        review response
    """
    request_id = request.headers.get(WF_REQUEST_ID_HEADER_NAME)
    if request_id is None:
        request_id = str(uuid.uuid4())

    # use without langgraph execution environment
    request_id_ctx.set(request_id)
    
    review_id = request_body.inputs.review_id
    
    hitl_service = WorkflowHitlService(workflow)
    try:
        # Get review information
        review = hitl_service.get_review(review_id)
        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Review {review_id} not found"
            )

        workflow_run_id = review.get("workflow_run_id")
        if not workflow_run_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Review does not have a workflow run ID"
            )
        init_state = {
            "sys_workflow_run_id": workflow_run_id,
            "request_id" : request_id

        }
        # Submit approval
        response_generator = hitl_service.approve(
            review_id=review_id,
            submitted_by=request_body.inputs.submitted_by,
            init_state=init_state
        )

        # if not success:
        #     raise HTTPException(
        #         status_code=status.HTTP_400_BAD_REQUEST,
        #         detail="Failed to approve review"
        #     )

        # logger.info(f"Review {review_id} approved successfully")

        # # Trigger workflow resume (if needed)
        # workflow_run_id = review.get("workflow_run_id")
        # try:
        #     from workflow.hitl_resume import resume_workflow_after_hitl
        #     resume_workflow_after_hitl(workflow_run_id, review_id)
        #     logger.info(f"Workflow {workflow_run_id} resumed after approval")
        # except Exception as e:
        #     logger.warning(f"Failed to auto-resume workflow: {e}")
        #     # Does not affect the main flow, continue returning success
        
        # return ReviewResponse(
        #     status="approve",
        #     message=json.dumps(response_data),
        #     review_id=review_id,
        #     #workflow_run_id=workflow_run_id
        # )
        return StreamingResponse(
            response_generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Workflow-Run-ID": workflow_run_id,
            },
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve review {request_body.inputs.review_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve review: {str(e)}"
        )


@router.post("/reviews/modify", summary="修改后批准")
def modify_review(
    request_http: Request,
    request: ModifyRequest,
    workflow: BaseWorkflow = Depends(validate_token_and_get_wf)
):
    """
    Approve after modification

    Args:
        request_http: HTTP request
        request: modify request (contains inputs.review_id)

    Returns:
        streaming response
    """
    request_id = request_http.headers.get(WF_REQUEST_ID_HEADER_NAME)
    if request_id is None:
        request_id = str(uuid.uuid4())

    # use without langgraph execution environment
    request_id_ctx.set(request_id)
    
    review_id = request.inputs.review_id
    
    hitl_service = WorkflowHitlService(workflow)
    try:
        # Get review information
        review = hitl_service.get_review(review_id)
        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Review {review_id} not found"
            )

        workflow_run_id = review.get("workflow_run_id")
        if not workflow_run_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Review does not have a workflow run ID"
            )

        init_state = {
            "sys_workflow_run_id": workflow_run_id,
            "request_id": request_id
        }

        # Submit modification (note: modify returns a generator)
        response_generator = hitl_service.modify(
            review_id=review_id,
            modified_data=request.inputs.modified_data,
            submitted_by=request.inputs.submitted_by,
            init_state=init_state
        )
        
        logger.info(f"Review {review_id} modified, streaming workflow output")
        
        return StreamingResponse(
            response_generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Workflow-Run-ID": workflow_run_id,
            },
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to modify review {review_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to modify review: {str(e)}"
        )


@router.post("/reviews/reject", summary="拒绝审核")
def reject_review(
    request_http: Request,
    request: RejectRequest,
    workflow: BaseWorkflow = Depends(validate_token_and_get_wf)
) -> ReviewResponse:
    """
    Reject review (the workflow will terminate directly, no streaming output returned)

    Args:
        request_http: HTTP request
        request: reject request (contains inputs.review_id)

    Returns:
        review response
    """
    request_id = request_http.headers.get(WF_REQUEST_ID_HEADER_NAME)
    if request_id is None:
        request_id = str(uuid.uuid4())

    # use without langgraph execution environment
    request_id_ctx.set(request_id)
    
    review_id = request.inputs.review_id
    
    hitl_service = WorkflowHitlService(workflow)
    try:
        # Get review information
        review = hitl_service.get_review(review_id)
        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Review {review_id} not found"
            )

        workflow_run_id = review.get("workflow_run_id")
        if not workflow_run_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Review does not have a workflow run ID"
            )

        init_state = {
            "sys_workflow_run_id": workflow_run_id,
            "request_id": request_id
        }

        # Submit rejection (note: reject terminates the workflow directly, just collect the generator)
        response_generator = hitl_service.reject(
            review_id=review_id,
            submitted_by=request.inputs.submitted_by,
            init_state=init_state
        )

        # Consume the generator (mainly the termination event)
        response_chunks = list(response_generator)
        
        logger.info(f"Review {review_id} rejected, workflow terminated with {len(response_chunks)} events")
        
        return ReviewResponse(
            status="reject",
            message=json.dumps({
                "success": True,
                "review_id": review_id,
                "workflow_run_id": workflow_run_id,
                "workflow_terminated": True,
                "events_count": len(response_chunks)
            }),
            review_id=review_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reject review {review_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reject review: {str(e)}"
        )


#decrepted
@router.post("/workflows/{workflow_run_id}/resume", summary="手动恢复工作流")
def resume_workflow(
    workflow_run_id: str,
    request: ResumeRequest,
    workflow: BaseWorkflow = Depends(validate_token_and_get_wf)
) -> Dict[str, Any]:
    """
    Manually resume workflow

    Args:
        workflow_run_id: workflow run ID
        request: resume request (contains inputs.review_id)

    Returns:
        resume result
    """
    try:
        review_id = request.inputs.review_id

        # Verify whether the review has been completed
        review = WorkflowHitlService(workflow).get_review(review_id)
        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Review {review_id} not found"
            )

        if review["status"] == "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Review is still pending, cannot resume workflow"
            )

        # Resume the workflow
        from goalflow.workflow.hitl_resume import resume_workflow_after_hitl
        result = resume_workflow_after_hitl(workflow_run_id, review_id)
        
        logger.info(f"Workflow {workflow_run_id} resumed successfully")
        
        return {
            "status": "resumed",
            "message": "Workflow resumed successfully",
            "workflow_run_id": workflow_run_id,
            "review_id": review_id,
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume workflow {workflow_run_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume workflow: {str(e)}"
        )


@router.get("/health", summary="健康检查")
def health_check():
    """HITL API health check"""
    return {
        "status": "healthy",
        "service": "HITL API",
        "timestamp": datetime.now().isoformat()
    }


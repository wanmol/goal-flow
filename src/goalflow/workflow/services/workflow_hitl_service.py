"""
HITL 工作流控制器
管理 HITL 审核流程的暂停、恢复和状态查询
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
    """HITL(human in the loop) 工作流控制器"""
    def __init__(self, workflow: BaseWorkflow[GenericState]):
        self.workflow = workflow

    def get_pending_reviews(self, workflow_run_id: str) -> List[Dict[str, Any]]:
        """
        获取工作流的待审核记录
        
        Args:
            workflow_run_id: 工作流运行ID
            
        Returns:
            List[Dict]: 待审核记录列表（转换为字典）
        """
        reviews = HITLReviewDB.get_pending_by_workflow_run_id(workflow_run_id)
        
        return [self._review_to_dict(review) for review in reviews]
    
    def get_review(self, review_id: str) -> Optional[Dict[str, Any]]:
        """
        获取单个审核记录
        
        Args:
            review_id: 审核ID
            
        Returns:
            Optional[Dict]: 审核记录（转换为字典）或 None
        """
        review = HITLReviewDB.get_by_review_id(review_id)
        
        if review:
            return self._review_to_dict(review)
        return None
    
    def get_all_reviews(self, workflow_run_id: str) -> List[Dict[str, Any]]:
        """
        获取工作流的所有审核记录
        
        Args:
            workflow_run_id: 工作流运行ID
            
        Returns:
            List[Dict]: 所有审核记录列表
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
        提交审核结果
        
        Args:
            review_id: 审核ID
            action: 审核动作 (approve/modify/reject)
            modified_data: 修改后的数据（仅当 action=modify 时）
            submitted_by: 审核人ID
            
        Returns:
            bool: 是否提交成功
        """
        workflow_run_id = init_state.get("sys_workflow_run_id")
        # 验证 action
        if action not in ['approve', 'modify', 'reject']:
            logger.error(f"Invalid action: {action}")
            yield format_stream_chunk(
                # chunck_id暂时没有实际业务需求，前端也没有使用，临时赋值
                chunk_id=action,
                event_type="error",
                data={
                    "error_type": "invalid_action",
                    "workflow_run_id": workflow_run_id,
                },
                message=f"invalid_action: {action}",
                task_id=workflow_run_id,
            )
        
        # 如果是 modify，必须提供 modified_data
        if action == 'modify' and not modified_data:
            logger.error("Modified data is required for 'modify' action")
            yield format_stream_chunk(
                # chunck_id暂时没有实际业务需求，前端也没有使用，临时赋值
                chunk_id=action,
                event_type="error",
                data={
                    "error_type": "missing_modified_data`",
                    "workflow_run_id": workflow_run_id,
                },
                message="modified_data is required for 'modify' action",
                task_id=workflow_run_id,
            )
        
        # 更新审核状态
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

        # 获取审核记录
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
        
        # 获取原始框架数据
        # ✅ 处理 modified_data 的嵌套结构：{"research_framework": {...}}
        if modified_data and isinstance(modified_data, dict) and modified_data:  # 确保非空字典
            # 如果 modified_data 中包含 research_framework 字段，提取它
            if "research_framework" in modified_data:
                research_framework = modified_data.get("research_framework")
                # ✅ 如果提取的值为空，使用原始框架
                if not research_framework:
                    research_framework = review.data.get("research_framework") if review.data else None
            else:
                # 否则假设 modified_data 本身就是 research_framework
                research_framework = modified_data
        else:
            # 如果没有提供修改数据或为空，使用原始数据
            research_framework = review.data.get("research_framework") if review.data else None
        
        # 从 review.data 中恢复必需的上下文字段
        review_data = review.data if review.data else {}
        
        chat_service:ChatflowGenerateService = ChatflowGenerateService(self.workflow)
        
        # 执行恢复操作的后续节点可能有中断点
        chat_service.bind_interrupt_hook(self)
        
        # 构造恢复状态（包含所有必需字段）
        state_param = {
            "hitl_review_id" : review_id,
            "interrupt_id": review.interrupt_id,
            "research_framework": research_framework,
            "hitl_action" : action,
            # 通过checkpoint恢复断点前的状态
            "rt_thread_id" : thread_id,
            # 从 review.data 中恢复的上下文字段
            "sys_user_id": review_data.get("sys_user_id"),
            "sys_conversation_id": review_data.get("sys_conversation_id"),
            "sys_query": review_data.get("sys_query"),
            "input_variables": review_data.get("input_variables", {}),
            # ✅ 恢复时间参数（如果存在）
            "sys_current_date": review_data.get("sys_current_date"),
            "sys_current_datetime": review_data.get("sys_current_datetime"),
        }
        
        # init_state 中的值优先级更高（仅更新非空字段）
        for key, value in init_state.items():
            if value is not None:  # 只更新有值的字段
                state_param[key] = value

        try:
            response = chat_service.generate(
               state_param
            )
            
            # 流式返回结果
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
        批准审核（快捷方法）
        
        Args:
            review_id: 审核ID
            submitted_by: 审核人ID
            
        Returns:
            bool: 是否批准成功
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
        修改后批准（快捷方法）
        
        Args:
            review_id: 审核ID
            modified_data: 修改后的数据
            submitted_by: 审核人ID
            
        Returns:
            bool: 是否修改成功
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
        拒绝审核（快捷方法）
        
        Args:
            review_id: 审核ID
            submitted_by: 审核人ID
            
        Returns:
            bool: 是否拒绝成功
        """
        return self.submit_review(
            review_id=review_id,
            action='reject',
            submitted_by=submitted_by,
            init_state=init_state,
        )
    
    def cleanup_expired_reviews(self) -> int:
        """
        清理过期的待审核记录
        
        Returns:
            int: 清理的记录数量
        """
        count = HITLReviewDB.cleanup_expired()
        logger.info(f"Cleaned up {count} expired reviews")
        return count
    

    def get_workflow_status(self, workflow_run_id: str) -> Dict[str, Any]:
        """
        获取工作流的 HITL 状态
        
        Args:
            workflow_run_id: 工作流运行ID
            
        Returns:
            Dict: 工作流 HITL 状态信息
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
        将 Review 对象转换为字典
        
        Args:
            review: HITLReview 对象
            
        Returns:
            Dict: 审核记录字典
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
        
    #TODO 需要更新表aira_wf_hitl_review的字段interrupt_id
    def after_interrupt(self, interrupt: Interrupt) -> object:
        review_id = interrupt.value["review_id"]
        interrupt_id = interrupt.id
        
        logger.info(f"after_interrupt: review_id={review_id}, interrupt_id={interrupt_id}")
        
        HITLReviewDB.update_interrupt_id(review_id, interrupt_id)


# 便捷函数
def get_pending_reviews(workflow:BaseWorkflow,workflow_run_id: str) -> List[Dict[str, Any]]:
    """获取待审核记录（便捷函数）"""
    return WorkflowHitlService(workflow).get_pending_reviews(workflow_run_id)


def submit_feedback(
    workflow:BaseWorkflow,
    review_id: str,
    action: str,
    modified_data: Optional[Dict] = None,
    submitted_by: Optional[str] = None,
    init_state: Dict[str, Any] = {}
) -> bool:
    """提交审核结果（便捷函数，已废弃）"""
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
    """批准审核（便捷函数，已废弃）"""
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
    """修改后批准（便捷函数，已废弃）"""
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
    """拒绝审核（便捷函数，已废弃）"""
    return WorkflowHitlService(workflow).reject(
        review_id=review_id,
        submitted_by=submitted_by,
        init_state=init_state
    )


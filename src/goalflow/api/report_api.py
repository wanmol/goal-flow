"""
研报管理 API

提供研报查询、详情等接口
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel, Field
from goalflow.config import get_logger
from goalflow.service.report_service import ReportService

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/reports", tags=["reports"])


# ========== 请求体模型定义 ==========

class ListReportsRequest(BaseModel):
    """列出研报请求"""
    conversation_id: str = Field(..., description="会话ID")


class GetReportDetailRequest(BaseModel):
    """获取研报详情请求"""
    conversation_id: str = Field(..., description="会话ID")
    report_id: str = Field(..., description="研报ID")
    version: Optional[int] = Field(None, description="版本号（不传则返回最新版本）")


class ListReportVersionsRequest(BaseModel):
    """获取研报版本历史请求"""
    conversation_id: str = Field(..., description="会话ID")
    report_id: str = Field(..., description="研报ID")


@router.post("/list")
def list_reports(request: ListReportsRequest):
    """
    获取指定会话下的所有研报列表
    
    用途：
    - 前端展示研报选择器
    - 显示所有研报的卡片（标题、摘要、版本）
    - 高亮当前活跃的研报
    
    请求体:
        {
            "conversation_id": "会话ID"
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "total": 2,
                "active_report_id": "report_abc123",
                "reports": [...]
            }
        }
    """
    try:
        if not request.conversation_id:
            raise HTTPException(status_code=400, detail="conversation_id is required")
        
        reports = ReportService.list_reports(request.conversation_id)
        active_report_id = ReportService.get_active_report_id(request.conversation_id)
        
        # 标记活跃研报
        for report in reports:
            report["is_active"] = (report["report_id"] == active_report_id)
        
        return {
            "success": True,
            "data": {
                "total": len(reports),
                "active_report_id": active_report_id,
                "reports": reports
            }
        }
    except Exception as e:
        logger.error(f"Failed to list reports: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/detail")
def get_report_detail(request: GetReportDetailRequest):
    """
    获取研报详情（指定版本或最新版本）
    
    用途：
    - 查看完整报告内容
    - 查看历史版本
    
    请求体:
        {
            "conversation_id": "会话ID",
            "report_id": "研报ID",
            "version": 1  // 可选，不传则返回最新版本
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "report_id": "report_abc123",
                "title": "...",
                "topic": "...",
                "abstract": "...",
                "version": {...}
            }
        }
    """
    try:
        report = ReportService.get_report(
            request.conversation_id, 
            request.report_id, 
            request.version
        )
        
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        
        return {
            "success": True,
            "data": report
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get report detail: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/versions")
def list_report_versions(request: ListReportVersionsRequest):
    """
    获取研报的所有版本历史
    
    用途：
    - 查看版本变更历史
    - 比较不同版本
    - 回滚到历史版本
    
    请求体:
        {
            "conversation_id": "会话ID",
            "report_id": "研报ID"
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "report_id": "report_abc123",
                "total_versions": 3,
                "versions": [...]
            }
        }
    """
    try:
        versions = ReportService.get_report_versions(
            request.conversation_id, 
            request.report_id
        )
        
        if not versions:
            raise HTTPException(status_code=404, detail="Report not found")
        
        return {
            "success": True,
            "data": {
                "report_id": request.report_id,
                "total_versions": len(versions),
                "versions": versions
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list versions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


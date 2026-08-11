"""
Report management API

Provides interfaces for querying reports, viewing details, etc.
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel, Field
from goalflow.config import get_logger
from goalflow.service.report_service import ReportService

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/reports", tags=["reports"])


# ========== Request body model definitions ==========

class ListReportsRequest(BaseModel):
    """List reports request"""
    conversation_id: str = Field(..., description="会话ID")


class GetReportDetailRequest(BaseModel):
    """Get report detail request"""
    conversation_id: str = Field(..., description="会话ID")
    report_id: str = Field(..., description="研报ID")
    version: Optional[int] = Field(None, description="版本号（不传则返回最新版本）")


class ListReportVersionsRequest(BaseModel):
    """Get report version history request"""
    conversation_id: str = Field(..., description="会话ID")
    report_id: str = Field(..., description="研报ID")


@router.post("/list")
def list_reports(request: ListReportsRequest):
    """
    Get the list of all reports under a given conversation

    Purpose:
    - Frontend displays the report selector
    - Show cards for all reports (title, abstract, version)
    - Highlight the currently active report

    Request body:
        {
            "conversation_id": "conversation ID"
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

        # Mark the active report
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
    Get report details (specified version or latest version)

    Purpose:
    - View the full report content
    - View historical versions

    Request body:
        {
            "conversation_id": "conversation ID",
            "report_id": "report ID",
            "version": 1  // optional; if omitted, returns the latest version
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
    Get all version history of a report

    Purpose:
    - View the version change history
    - Compare different versions
    - Roll back to a historical version

    Request body:
        {
            "conversation_id": "conversation ID",
            "report_id": "report ID"
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


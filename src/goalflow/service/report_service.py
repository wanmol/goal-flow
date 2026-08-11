"""
Research report management service

Handles report creation, update, query, version management, and other operations
"""

import uuid
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from goalflow.config import get_logger
from goalflow.service.workflow_conversation_variables_service import WorkflowConversationVariablesService
from goalflow.model.wf_conv_variable import WorkflowConversationVariables

logger = get_logger(__name__)


class ReportService:
    """Research report management service"""
    
    @staticmethod
    def _get_data(conv_vars: WorkflowConversationVariables) -> Dict[str, Any]:
        """
        Get data from conversation variables and handle deserialization

        Args:
            conv_vars: conversation variable object

        Returns:
            the deserialized data dict
        """
        if not conv_vars:
            return {}
        
        data = conv_vars.data
        # If it is a string, it needs to be deserialized
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to deserialize conv_vars.data: {data[:100]}")
                return {}
        
        return data or {}
    
    @staticmethod
    def create_report(
        conversation_id: str,
        title: str,
        topic: str,
        abstract: str,
        content: str,
        research_framework: dict,
        research_results: list,
        references: Optional[dict] = None,  # ✅ in-text citations (filtered)
        all_references: Optional[dict] = None,  # ✅ new: all citation sources (unfiltered)
        user_id: str = ""
    ) -> dict:
        """
        Create a new research report

        Args:
            conversation_id: conversation ID
            title: report title
            topic: topic keywords
            abstract: abstract
            content: report content
            research_framework: research framework
            research_results: research results
            user_id: user ID

        Returns:
            {
                "report_id": "report_xxx",
                "version": 1,
                "created_at": "..."
            }
        """
        # 1. Generate the report ID
        report_id = f"report_{uuid.uuid4().hex[:12]}"

        # 2. Create the report data structure
        new_report = {
            "report_id": report_id,
            "title": title,
            "topic": topic,
            "abstract": abstract,
            "current_version": 1,
            "created_at": datetime.now().isoformat(),
            "last_updated_at": datetime.now().isoformat(),
            "versions": [
                {
                    "version": 1,
                    "content": content,
                    "research_framework": research_framework,
                    "research_results": research_results,
                    "references": references or {},  # ✅ in-text citations (filtered)
                    "all_references": all_references or {},  # ✅ all citation sources (unfiltered)
                    "generated_at": datetime.now().isoformat(),
                    "modification": None,  # initial version
                    "word_count": len(content)
                }
            ]
        }
        
        # 3. Get the existing conversation_variables
        conv_vars = WorkflowConversationVariablesService.get_by_conversation_id(
            conversation_id
        )
        
        data = ReportService._get_data(conv_vars)
        
        # 4. Update the report collection
        if "reports" not in data:
            data["reports"] = {}
        if "report_index" not in data:
            data["report_index"] = {}
        if "metadata" not in data:
            data["metadata"] = {}
        
        data["reports"][report_id] = new_report
        data["active_report_id"] = report_id  # set as the current active report
        data["report_index"][topic] = report_id  # add topic index
        data["metadata"]["total_reports"] = len(data["reports"])
        data["metadata"]["last_activity"] = datetime.now().isoformat()
        
        # 5. Persist to the database
        if conv_vars:
            WorkflowConversationVariablesService.update_by_conversation_id(
                conv_vars=WorkflowConversationVariables(
                    conversation_id=conversation_id,
                    data=data,
                    last_updater_id=user_id
                )
            )
        else:
            WorkflowConversationVariablesService.create(
                conversation_id=conversation_id,
                data=data,
                creator_id=user_id
            )
        
        logger.info(f"Created report {report_id} for conversation {conversation_id}")
        
        return {
            "report_id": report_id,
            "version": 1,
            "created_at": new_report["created_at"]
        }
    
    @staticmethod
    def add_version(
        conversation_id: str,
        report_id: str,
        title: Optional[str],
        abstract: Optional[str],
        content: str,
        research_framework: dict,
        research_results: list,
        references: Optional[dict],  # ✅ in-text citations (filtered)
        modification_instruction: str,
        all_references: Optional[dict] = None,  # ✅ new: all citation sources (unfiltered)
        user_id: str = ""
    ) -> dict:
        """
        Add a new version to a research report

        Args:
            conversation_id: conversation ID
            report_id: report ID
            title: report title (optional, updates the title)
            abstract: abstract (optional, updates the abstract)
            content: report content
            research_framework: research framework
            research_results: research results
            modification_instruction: modification instruction
            user_id: user ID

        Returns:
            {
                "report_id": "report_xxx",
                "version": 2,
                "created_at": "..."
            }
        """
        # 1. Get the existing data
        conv_vars = WorkflowConversationVariablesService.get_by_conversation_id(
            conversation_id
        )
        
        data = ReportService._get_data(conv_vars)
        if not data or "reports" not in data:
            raise ValueError(f"Report {report_id} not found")
        report = data["reports"].get(report_id)
        
        if not report:
            raise ValueError(f"Report {report_id} not found")
        
        # 2. Update the title and abstract (if provided)
        if title:
            report["title"] = title
        if abstract:
            report["abstract"] = abstract
        
        # 3. Create a new version
        new_version_number = report["current_version"] + 1
        new_version = {
            "version": new_version_number,
            "content": content,
            "research_framework": research_framework,
            "research_results": research_results,
            "references": references or {},  # ✅ in-text citations (filtered)
            "all_references": all_references or {},  # ✅ all citation sources (unfiltered)
            "generated_at": datetime.now().isoformat(),
            "modification": modification_instruction,
            "word_count": len(content)
        }
        
        # 4. Add to the version history
        report["versions"].append(new_version)
        
        # 5. Limit the number of versions in the history (keep the most recent 10)
        if len(report["versions"]) > 10:
            report["versions"] = report["versions"][-10:]
            # Renumber
            for i, v in enumerate(report["versions"], start=new_version_number-9):
                v["version"] = i
        
        # 6. Update the metadata
        report["current_version"] = new_version_number
        report["last_updated_at"] = datetime.now().isoformat()
        data["metadata"]["last_activity"] = datetime.now().isoformat()
        
        # 7. Persist
        WorkflowConversationVariablesService.update_by_conversation_id(
            conv_vars=WorkflowConversationVariables(
                conversation_id=conversation_id,
                data=data,
                last_updater_id=user_id
            )
        )
        
        logger.info(f"Added version {new_version_number} to report {report_id}")
        
        return {
            "report_id": report_id,
            "version": new_version_number,
            "created_at": new_version["generated_at"]
        }
    
    @staticmethod
    def get_report(
        conversation_id: str, 
        report_id: str, 
        version: Optional[int] = None
    ) -> Optional[dict]:
        """
        Get a research report (a specific version or the latest version)

        Args:
            conversation_id: conversation ID
            report_id: report ID
            version: version number (optional; if omitted, returns the latest version)

        Returns:
            {
                "report_id": "report_xxx",
                "title": "...",
                "topic": "...",
                "abstract": "...",
                "version": {...}
            }
        """
        conv_vars = WorkflowConversationVariablesService.get_by_conversation_id(
            conversation_id
        )
        
        data = ReportService._get_data(conv_vars)
        if not data or "reports" not in data:
            return None
        
        report = data["reports"].get(report_id)
        if not report:
            return None
        
        # If no version is specified, return the latest version
        if version is None:
            version = report["current_version"]
        
        # Find the specified version
        for v in report["versions"]:
            if v["version"] == version:
                return {
                    "report_id": report_id,
                    "title": report["title"],
                    "topic": report["topic"],
                    "abstract": report["abstract"],
                    "version": v
                }
        
        return None
    
    @staticmethod
    def switch_active_report(
        conversation_id: str, 
        report_id: str
    ) -> bool:
        """
        Switch the current active research report

        Args:
            conversation_id: conversation ID
            report_id: report ID

        Returns:
            bool: whether it succeeded
        """
        conv_vars = WorkflowConversationVariablesService.get_by_conversation_id(
            conversation_id
        )
        
        data = ReportService._get_data(conv_vars)
        if not data or "reports" not in data:
            return False
        
        if report_id not in data["reports"]:
            return False
        
        # Update the active report
        data["active_report_id"] = report_id
        
        # Persist
        WorkflowConversationVariablesService.update_by_conversation_id(
            conv_vars=WorkflowConversationVariables(
                conversation_id=conversation_id,
                data=data
            )
        )
        
        logger.info(f"Switched active report to {report_id} for conversation {conversation_id}")
        
        return True
    
    @staticmethod
    def get_active_report_id(conversation_id: str) -> Optional[str]:
        """
        Get the ID of the current active research report

        Args:
            conversation_id: conversation ID

        Returns:
            str: the active report ID, or None if it does not exist
        """
        conv_vars = WorkflowConversationVariablesService.get_by_conversation_id(
            conversation_id
        )
        
        data = ReportService._get_data(conv_vars)
        if data and "active_report_id" in data:
            return data["active_report_id"]
        
        return None
    
    @staticmethod
    def list_reports(conversation_id: str) -> List[dict]:
        """
        List all research reports under a conversation

        Args:
            conversation_id: conversation ID

        Returns:
            List[dict]: list of research reports
        """
        conv_vars = WorkflowConversationVariablesService.get_by_conversation_id(
            conversation_id
        )
        
        data = ReportService._get_data(conv_vars)
        if not data or "reports" not in data:
            return []
        
        reports = []
        for report_id, report_data in data["reports"].items():
            # Get the word count of the latest version
            latest_version = report_data.get("versions", [{}])[-1]
            word_count = latest_version.get("word_count", 0)
            
            reports.append({
                "report_id": report_id,
                "title": report_data.get("title", ""),
                "topic": report_data.get("topic", ""),
                "abstract": report_data.get("abstract", ""),
                "current_version": report_data.get("current_version", 1),
                "total_versions": len(report_data.get("versions", [])),
                "word_count": word_count,
                "created_at": report_data.get("created_at", ""),
                "last_updated_at": report_data.get("last_updated_at", "")
            })
        
        # Sort by last updated time
        reports.sort(key=lambda x: x["last_updated_at"], reverse=True)
        
        return reports
    
    @staticmethod
    def get_report_versions(conversation_id: str, report_id: str) -> Optional[List[dict]]:
        """
        Get the full version history of a research report

        Args:
            conversation_id: conversation ID
            report_id: report ID

        Returns:
            List[dict]: list of versions
        """
        conv_vars = WorkflowConversationVariablesService.get_by_conversation_id(
            conversation_id
        )
        
        data = ReportService._get_data(conv_vars)
        if not data or "reports" not in data:
            return None
        
        report = data["reports"].get(report_id)
        if not report:
            return None
        
        # Return the version history (without full content, only metadata)
        versions = []
        for v in report.get("versions", []):
            versions.append({
                "version": v.get("version"),
                "generated_at": v.get("generated_at"),
                "modification": v.get("modification"),
                "word_count": v.get("word_count", 0)
            })
        
        return versions


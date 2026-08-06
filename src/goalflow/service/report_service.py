"""
研报管理服务

负责研报的创建、更新、查询、版本管理等操作
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
    """研报管理服务"""
    
    @staticmethod
    def _get_data(conv_vars: WorkflowConversationVariables) -> Dict[str, Any]:
        """
        从 conversation variables 中获取数据，并处理反序列化
        
        Args:
            conv_vars: 会话变量对象
            
        Returns:
            反序列化后的数据字典
        """
        if not conv_vars:
            return {}
        
        data = conv_vars.data
        # 如果是字符串，需要反序列化
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
        references: Optional[dict] = None,  # ✅ 文中引用（已过滤）
        all_references: Optional[dict] = None,  # ✅ 新增：所有引用来源（未过滤）
        user_id: str = ""
    ) -> dict:
        """
        创建新研报
        
        Args:
            conversation_id: 会话ID
            title: 报告标题
            topic: 主题关键词
            abstract: 摘要
            content: 报告内容
            research_framework: 研究框架
            research_results: 研究结果
            user_id: 用户ID
        
        Returns:
            {
                "report_id": "report_xxx",
                "version": 1,
                "created_at": "..."
            }
        """
        # 1. 生成研报 ID
        report_id = f"report_{uuid.uuid4().hex[:12]}"
        
        # 2. 创建研报数据结构
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
                    "references": references or {},  # ✅ 文中引用（已过滤）
                    "all_references": all_references or {},  # ✅ 所有引用来源（未过滤）
                    "generated_at": datetime.now().isoformat(),
                    "modification": None,  # 初始版本
                    "word_count": len(content)
                }
            ]
        }
        
        # 3. 获取现有 conversation_variables
        conv_vars = WorkflowConversationVariablesService.get_by_conversation_id(
            conversation_id
        )
        
        data = ReportService._get_data(conv_vars)
        
        # 4. 更新研报集合
        if "reports" not in data:
            data["reports"] = {}
        if "report_index" not in data:
            data["report_index"] = {}
        if "metadata" not in data:
            data["metadata"] = {}
        
        data["reports"][report_id] = new_report
        data["active_report_id"] = report_id  # 设置为当前活跃研报
        data["report_index"][topic] = report_id  # 添加主题索引
        data["metadata"]["total_reports"] = len(data["reports"])
        data["metadata"]["last_activity"] = datetime.now().isoformat()
        
        # 5. 持久化到数据库
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
        references: Optional[dict],  # ✅ 文中引用（已过滤）
        modification_instruction: str,
        all_references: Optional[dict] = None,  # ✅ 新增：所有引用来源（未过滤）
        user_id: str = ""
    ) -> dict:
        """
        为研报添加新版本
        
        Args:
            conversation_id: 会话ID
            report_id: 研报ID
            title: 报告标题（可选，更新标题）
            abstract: 摘要（可选，更新摘要）
            content: 报告内容
            research_framework: 研究框架
            research_results: 研究结果
            modification_instruction: 修改指令
            user_id: 用户ID
        
        Returns:
            {
                "report_id": "report_xxx",
                "version": 2,
                "created_at": "..."
            }
        """
        # 1. 获取现有数据
        conv_vars = WorkflowConversationVariablesService.get_by_conversation_id(
            conversation_id
        )
        
        data = ReportService._get_data(conv_vars)
        if not data or "reports" not in data:
            raise ValueError(f"Report {report_id} not found")
        report = data["reports"].get(report_id)
        
        if not report:
            raise ValueError(f"Report {report_id} not found")
        
        # 2. 更新标题和摘要（如果提供）
        if title:
            report["title"] = title
        if abstract:
            report["abstract"] = abstract
        
        # 3. 创建新版本
        new_version_number = report["current_version"] + 1
        new_version = {
            "version": new_version_number,
            "content": content,
            "research_framework": research_framework,
            "research_results": research_results,
            "references": references or {},  # ✅ 文中引用（已过滤）
            "all_references": all_references or {},  # ✅ 所有引用来源（未过滤）
            "generated_at": datetime.now().isoformat(),
            "modification": modification_instruction,
            "word_count": len(content)
        }
        
        # 4. 添加到版本历史
        report["versions"].append(new_version)
        
        # 5. 限制版本历史数量（保留最近10个）
        if len(report["versions"]) > 10:
            report["versions"] = report["versions"][-10:]
            # 重新编号
            for i, v in enumerate(report["versions"], start=new_version_number-9):
                v["version"] = i
        
        # 6. 更新元数据
        report["current_version"] = new_version_number
        report["last_updated_at"] = datetime.now().isoformat()
        data["metadata"]["last_activity"] = datetime.now().isoformat()
        
        # 7. 持久化
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
        获取研报（指定版本或最新版本）
        
        Args:
            conversation_id: 会话ID
            report_id: 研报ID
            version: 版本号（可选，不传则返回最新版本）
        
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
        
        # 如果未指定版本，返回最新版本
        if version is None:
            version = report["current_version"]
        
        # 查找指定版本
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
        切换当前活跃研报
        
        Args:
            conversation_id: 会话ID
            report_id: 研报ID
        
        Returns:
            bool: 是否成功
        """
        conv_vars = WorkflowConversationVariablesService.get_by_conversation_id(
            conversation_id
        )
        
        data = ReportService._get_data(conv_vars)
        if not data or "reports" not in data:
            return False
        
        if report_id not in data["reports"]:
            return False
        
        # 更新活跃研报
        data["active_report_id"] = report_id
        
        # 持久化
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
        获取当前活跃的研报 ID
        
        Args:
            conversation_id: 会话ID
        
        Returns:
            str: 活跃研报ID，如果不存在则返回 None
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
        列出会话下的所有研报
        
        Args:
            conversation_id: 会话ID
        
        Returns:
            List[dict]: 研报列表
        """
        conv_vars = WorkflowConversationVariablesService.get_by_conversation_id(
            conversation_id
        )
        
        data = ReportService._get_data(conv_vars)
        if not data or "reports" not in data:
            return []
        
        reports = []
        for report_id, report_data in data["reports"].items():
            # 获取最新版本的字数
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
        
        # 按最后更新时间排序
        reports.sort(key=lambda x: x["last_updated_at"], reverse=True)
        
        return reports
    
    @staticmethod
    def get_report_versions(conversation_id: str, report_id: str) -> Optional[List[dict]]:
        """
        获取研报的所有版本历史
        
        Args:
            conversation_id: 会话ID
            report_id: 研报ID
        
        Returns:
            List[dict]: 版本列表
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
        
        # 返回版本历史（不包含完整内容，只有元数据）
        versions = []
        for v in report.get("versions", []):
            versions.append({
                "version": v.get("version"),
                "generated_at": v.get("generated_at"),
                "modification": v.get("modification"),
                "word_count": v.get("word_count", 0)
            })
        
        return versions


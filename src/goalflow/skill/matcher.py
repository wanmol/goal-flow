"""
Skill matcher: uses LLM to match user query to the best skill(s).
"""

import json
import os
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from goalflow.config import get_logger
from goalflow.skill.models import MatchResult, SkillMatchRequest, SkillMetadata

logger = get_logger(__name__)

SKILL_MATCH_SYSTEM_PROMPT = """你是一个技能匹配引擎。根据用户的查询，从可用技能列表中选择最匹配的技能。

规则：
1. 仔细分析用户查询的意图
2. 将用户意图与每个技能的名称和描述进行比较
3. 返回匹配度最高的技能（可以返回多个）
4. 如果没有任何技能匹配，返回空数组 []
5. confidence 取值范围 0.0-1.0，表示匹配置信度

必须严格返回以下 JSON 格式（不要包含其他内容）：
[
  {{
    "skill_id": "技能ID",
    "skill_name": "技能名称",
    "confidence": 0.85,
    "reason": "匹配原因简述"
  }}
]"""

SKILL_MATCH_USER_PROMPT = """用户查询：{query}

可用技能列表：
{skills_json}"""


class SkillMatcher:
    """Uses LLM to match user queries to skills based on metadata."""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
    ):
        self._provider = provider or os.getenv("SKILL_MATCH_PROVIDER", "qwen")
        self._model = model or os.getenv("SKILL_MATCH_MODEL", "qwen-turbo")
        self._temperature = temperature
        self._llm = None

    def _get_llm(self):
        """Lazy-create LLM instance."""
        if self._llm is None:
            from goalflow.llm import LLM

            self._llm = LLM.create(
                provider=self._provider,
                model=self._model,
                temperature=self._temperature,
            )
        return self._llm

    def match(
        self,
        request: SkillMatchRequest,
        metadata: List[SkillMetadata],
    ) -> List[MatchResult]:
        """Match a user query against available skills using LLM."""
        if not metadata:
            return []

        messages = self._build_messages(request.query, metadata)

        try:
            llm = self._get_llm()
            response = llm.invoke(messages)
            content = response.content
        except Exception as e:
            logger.error("skill matching LLM call failed", error=str(e))
            return []

        results = self._parse_response(content)

        # Filter by threshold and sort by confidence
        results = [r for r in results if r.confidence >= request.threshold]
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[: request.top_k]

    def _build_messages(self, query: str, metadata: List[SkillMetadata]) -> list:
        """Build LLM messages for skill matching."""
        skills_data = [
            {
                "skill_id": m.skill_id,
                "name": m.name,
                "description": m.description,
            }
            for m in metadata
        ]
        skills_json = json.dumps(skills_data, ensure_ascii=False, indent=2)

        return [
            SystemMessage(content=SKILL_MATCH_SYSTEM_PROMPT),
            HumanMessage(
                content=SKILL_MATCH_USER_PROMPT.format(
                    query=query, skills_json=skills_json
                )
            ),
        ]

    def _parse_response(self, content: str) -> List[MatchResult]:
        """Parse LLM JSON response into MatchResult list."""
        try:
            cleaned = content.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)
        except (json.JSONDecodeError, Exception) as e:
            logger.error("failed to parse skill match response", content=content, error=str(e))
            return []

        if not isinstance(data, list):
            data = [data]

        results = []
        for item in data:
            try:
                results.append(MatchResult(**item))
            except Exception as e:
                logger.warning("invalid match result item", item=item, error=str(e))
        return results

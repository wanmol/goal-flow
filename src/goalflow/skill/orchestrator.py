"""
Skill orchestrator: single entry point from user query to final system prompt.
"""

from typing import List, Optional, Tuple

from goalflow.config import get_logger
from goalflow.skill.models import MatchResult, SkillContent, SkillMatchRequest
from goalflow.skill.registry import SkillRegistry
from goalflow.skill.matcher import SkillMatcher
from goalflow.skill.loader import SkillLoader
from goalflow.skill.prompt_builder import SystemPromptBuilder

logger = get_logger(__name__)


class SkillOrchestrator:
    """
    Orchestrates the full skill pipeline: match → load → build prompt.
    
    ## Examples  below is a basic usage ， from query to system prompt
    
    from goalflow.skill import SkillOrchestrator

    # Quick creation
    orchestrator = SkillOrchestrator.create_default()

    # One step: query → final system prompt
    prompt = orchestrator.build_prompt(
        query="What's the weather in Shanghai",
        base_prompt="You are an intelligent assistant.",
    )

    # If intermediate results are needed (match details + skill content)
    matches, contents = orchestrator.match_and_load("Shanghai weather")

    """

    def __init__(
        self,
        registry: SkillRegistry,
        matcher: SkillMatcher,
        loader: SkillLoader,
        prompt_builder: SystemPromptBuilder,
    ):
        self._registry = registry
        self._matcher = matcher
        self._loader = loader
        self._prompt_builder = prompt_builder

    @classmethod
    def create_default(cls, skills_dir: Optional[str] = None) -> "SkillOrchestrator":
        """Factory: create an orchestrator with default components."""
        
        #  SkillRegistry initialization sets skills_dir to the default value "skills", so there is no need to check here
        # from pathlib import Path
        # if skills_dir is None:
        #     skills_dir = "skills"
            
        # if not Path(skills_dir).exists():
        #     raise ValueError(f"skills_dir {skills_dir} does not exist")
        
        registry = SkillRegistry(skills_dir=skills_dir)
        return cls(
            registry=registry,
            matcher=SkillMatcher(),
            loader=SkillLoader(registry),
            prompt_builder=SystemPromptBuilder(registry),
        )

    def match_and_load(
        self,
        query: str,
        top_k: int = 1,
        threshold: float = 0.3,
    ) -> Tuple[List[MatchResult], List[SkillContent]]:
        """Match query to skills and load their content. Returns (matches, skill_contents)."""
        all_metadata = self._registry.get_all_metadata()
        if not all_metadata:
            return [], []

        request = SkillMatchRequest(query=query, top_k=top_k, threshold=threshold)
        matches = self._matcher.match(request, all_metadata)
        if not matches:
            return [], []

        skill_contents = self._loader.load_multiple([m.skill_id for m in matches])
        return matches, skill_contents

    def build_prompt(
        self,
        query: str,
        base_prompt: str,
        top_k: int = 1,
        threshold: float = 0.3,
    ) -> str:
        """Full pipeline: query → matched system prompt."""
        _, skill_contents = self.match_and_load(query, top_k=top_k, threshold=threshold)

        return self._prompt_builder.build_system_prompt(
            base_prompt=base_prompt,
            matched_skills=skill_contents if skill_contents else None,
        )

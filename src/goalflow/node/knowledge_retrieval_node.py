from typing import Any, Optional, Sequence

from langgraph.types import Command

from goalflow.node import BaseNode, NodeOutput
from goalflow.state import GenericState
from goalflow.tool.utils import VariableResolver
from goalflow.knowledge import RetrievalConfig, get_retriever
from goalflow.config import get_logger

logger = get_logger(__name__)


class KnowledgeRetrievalNode(BaseNode):
    """Retrieve knowledge chunks for the node's query via a pluggable backend.

    The node itself is backend-agnostic: it resolves the query text from state,
    builds a :class:`~goalflow.knowledge.RetrievalConfig` from its parsed
    configuration, and delegates to the process-wide retriever
    (:func:`goalflow.knowledge.get_retriever`). Which backend runs is decided by
    environment configuration (see ``goalflow.knowledge.factory``).

    On retrieval failure it follows the standard node error strategy
    (``default-value`` / ``fail-branch``) and, when none is set, re-raises — so a
    misconfigured knowledge node fails loudly instead of silently returning an
    empty result the way the previous stub did.

    Output (written under this node id):
        result:  list of chunk dicts {content, title, url, score, metadata}
        content: the concatenated chunk contents (convenience for prompt use)
    """

    def __init__(
        self,
        *,
        dataset_ids: Optional[Sequence[str]] = None,
        query_variable_selector: Optional[Sequence[str]] = None,
        retrieval_config: Optional[dict[str, Any]] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.dataset_ids = list(dataset_ids or [])
        self.query_variable_selector = list(query_variable_selector or [])
        # Raw parsed config (retrieval_mode, multiple_retrieval_config, ...);
        # normalized into RetrievalConfig at call time.
        self.retrieval_config = retrieval_config or {}

    def _resolve_query(self, state: GenericState) -> str:
        """Resolve the query text from the configured selector, or fall back."""
        if self.query_variable_selector:
            value = VariableResolver.resolve_value_selector(
                self.query_variable_selector, state
            )
            if value:
                return value if isinstance(value, str) else str(value)
        # Fall back to the system query so the node still functions when the DSL
        # omits an explicit selector.
        return state.get("sys_query", "") or ""

    def call(self, state: GenericState) -> NodeOutput:
        try:
            query = self._resolve_query(state)

            config = RetrievalConfig.from_node_config({
                "dataset_ids": self.dataset_ids,
                **self.retrieval_config,
            })

            logger.info(
                f"{self.formatted_name} knowledge retrieval start",
                dataset_ids=self.dataset_ids,
                retrieval_mode=config.retrieval_mode,
                top_k=config.top_k,
            )

            chunks = get_retriever().retrieve(query, config)

            result = [c.to_output() for c in chunks]
            content = "\n\n".join(c.content for c in chunks if c.content)

            update = VariableResolver.format_output(
                node_id=self.id,
                outputs={"result": result, "content": content},
            )
            return Command(update=update, goto=self.next_node_ids)

        except Exception as e:
            logger.error(
                f"{self.formatted_name} knowledge retrieval error",
                error=str(e),
                exc_info=True,
            )
            return self._handle_error(e)

    def _handle_error(self, e: Exception) -> NodeOutput:
        """Route the failure through the node's error strategy.

        Mirrors the pattern used by the other nodes; when no strategy is set the
        error propagates so the failure is visible rather than swallowed.
        """
        if not self.error_strategy:
            raise e

        strategy = str(self.error_strategy)
        if strategy in ("default-value", "ErrorStrategy.DEFAULT_VALUE"):
            default_content = ""
            if self.default_value:
                # Support both dict-shaped and DefaultValue-shaped entries.
                first = self.default_value[0]
                default_content = getattr(first, "value", None)
                if default_content is None and isinstance(first, dict):
                    default_content = first.get("value", "")
            update = VariableResolver.format_output(
                node_id=self.id,
                outputs={"result": [], "content": default_content or ""},
            )
            return Command(update=update, goto=self.next_node_ids)

        if strategy in ("fail-branch", "ErrorStrategy.FAIL_BRANCH"):
            return Command(
                update={"node_id": self.id, "source_handle": "fail-branch"},
                goto=self.fail_branch_node_ids,
            )

        raise e

"""Mapping table from n8n node types to goalflow node kinds.

Coverage strategy: core subset + placeholder fallback.
Any type not in the mapping table goes to ``PLACEHOLDER``, generating a no-op placeholder node and adding it to the warning list.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional


class GoloNodeKind(Enum):
    """The goalflow node kind that is the conversion target."""

    START = "start"
    END = "end"
    HTTP_REQUEST = "http_request"
    IF_ELSE = "if_else"
    CODE = "code"
    LLM = "llm"
    AGENT = "agent"
    PLACEHOLDER = "placeholder"


# n8n short type name (with the namespace prefix removed) → goalflow node kind.
# See N8nNode.short_type for short type names:
#   n8n-nodes-base.httpRequest        → httpRequest
#   @n8n/n8n-nodes-langchain.agent    → agent
N8N_SHORT_TYPE_TO_KIND = {
    # ── trigger / start ──
    "start": GoloNodeKind.START,
    "manualTrigger": GoloNodeKind.START,
    "webhook": GoloNodeKind.START,
    "scheduleTrigger": GoloNodeKind.START,
    "cron": GoloNodeKind.START,
    "trigger": GoloNodeKind.START,
    "chatTrigger": GoloNodeKind.START,
    "executeWorkflowTrigger": GoloNodeKind.START,
    "formTrigger": GoloNodeKind.START,
    "emailReadImap": GoloNodeKind.START,
    # ── http ──
    "httpRequest": GoloNodeKind.HTTP_REQUEST,
    # ── branch ──
    "if": GoloNodeKind.IF_ELSE,
    "filter": GoloNodeKind.IF_ELSE,
    # ── code ──
    "code": GoloNodeKind.CODE,
    "function": GoloNodeKind.CODE,
    "functionItem": GoloNodeKind.CODE,
    # ── LLM / Agent (langchain) ──
    "agent": GoloNodeKind.AGENT,
    "openAi": GoloNodeKind.LLM,
    "lmChatOpenAi": GoloNodeKind.LLM,
    "chainLlm": GoloNodeKind.LLM,
    # ── terminal ──
    "respondToWebhook": GoloNodeKind.END,
    "noOp": GoloNodeKind.END,
}


def map_node_kind(short_type: str) -> GoloNodeKind:
    """Map an n8n short type name to a goalflow node kind; unknown types return PLACEHOLDER."""
    return N8N_SHORT_TYPE_TO_KIND.get(short_type, GoloNodeKind.PLACEHOLDER)


def is_supported(short_type: str) -> bool:
    """Whether this n8n type has a real goalflow node (not a placeholder)."""
    return short_type in N8N_SHORT_TYPE_TO_KIND

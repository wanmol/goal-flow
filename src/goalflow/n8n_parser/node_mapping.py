"""n8n 节点类型 → goalflow 节点种类的映射表。

覆盖策略：核心子集 + 占位兜底。
映射表里没有的类型一律走 ``PLACEHOLDER``，生成占位 no-op 节点并记入警告清单。
"""
from __future__ import annotations

from enum import Enum
from typing import Optional


class GoloNodeKind(Enum):
    """转换目标的 goalflow 节点种类。"""

    START = "start"
    END = "end"
    HTTP_REQUEST = "http_request"
    IF_ELSE = "if_else"
    CODE = "code"
    LLM = "llm"
    AGENT = "agent"
    PLACEHOLDER = "placeholder"


# n8n 短类型名（去掉命名空间前缀后）→ goalflow 节点种类。
# 短类型名见 N8nNode.short_type：
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
    # ── 分支 ──
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
    # ── 终端 ──
    "respondToWebhook": GoloNodeKind.END,
    "noOp": GoloNodeKind.END,
}


def map_node_kind(short_type: str) -> GoloNodeKind:
    """把 n8n 短类型名映射到 goalflow 节点种类，未知类型返回 PLACEHOLDER。"""
    return N8N_SHORT_TYPE_TO_KIND.get(short_type, GoloNodeKind.PLACEHOLDER)


def is_supported(short_type: str) -> bool:
    """该 n8n 类型是否有真实的 goalflow 节点对应（非占位）。"""
    return short_type in N8N_SHORT_TYPE_TO_KIND

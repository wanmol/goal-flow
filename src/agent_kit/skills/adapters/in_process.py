"""InProcessAdapter：把 SkillManifest.entry_point (kind=in_process) 转成 LangChain Tool。

约定：
- ``entry_point.target`` 格式：``"module.path:function_name"``
  例如 ``"my_skill_pkg.weather:get_weather"``
- 函数签名任意；LangChain ``@tool`` 会从签名 + 类型注解 + docstring 自动生成 schema
- tool 名优先级：
    1. ``entry_point.tool_name``（可选字段，PR3 加入）
    2. ``manifest.skill_id``（kebab-case 目录名，一定是 ASCII，LangChain 兼容）
- tool description：
    1. 函数 docstring（LangChain 优先用这个）
    2. 退化到 ``manifest.description``

错误处理：
- import 失败 / 函数不存在 / 非 callable / 缺 docstring → 静默 skip + warn log
- 一个 skill 出错不影响其它 skill
"""
from __future__ import annotations

import importlib
import logging
from typing import Any, Optional

from agent_kit.skills.models import SkillManifest

logger = logging.getLogger(__name__)


class InProcessAdapter:
    """无状态适配器；纯函数式 API。"""

    @classmethod
    def materialize(cls, manifest: SkillManifest) -> Optional[Any]:
        """把单个 manifest 转成 LangChain Tool；失败返回 None。"""
        ep = manifest.entry_point
        if ep is None:
            logger.warning(
                "InProcessAdapter: skill %r has no entry_point; skipping",
                manifest.skill_id,
            )
            return None
        if ep.kind != "in_process":
            logger.warning(
                "InProcessAdapter: skill %r entry_point.kind=%r is not in_process; skipping",
                manifest.skill_id,
                ep.kind,
            )
            return None

        fn = _resolve_target(ep.target, manifest.skill_id)
        if fn is None:
            return None

        # 尝试取 tool_name；EntryPoint 没声明就用 skill_id
        tool_name = getattr(ep, "tool_name", None) or manifest.skill_id

        # 用 LangChain @tool 包装
        try:
            from langchain_core.tools import tool as lc_tool

            # 如果函数没 docstring，用 manifest.description 兜底（LangChain 要求 description）
            if not fn.__doc__:
                fn.__doc__ = manifest.description or f"Skill: {manifest.name}"

            return lc_tool(tool_name)(fn)
        except Exception as e:
            logger.warning(
                "InProcessAdapter: failed to wrap skill %r as LangChain tool: %s",
                manifest.skill_id,
                e,
            )
            return None

    @classmethod
    def materialize_many(cls, manifests: list[SkillManifest]) -> list[Any]:
        """批量；只返回成功 materialize 的 tool。"""
        tools = []
        for m in manifests:
            t = cls.materialize(m)
            if t is not None:
                tools.append(t)
        return tools


def _resolve_target(target: str, skill_id: str):
    """``"pkg.mod:func"`` → 可调用对象。失败返回 None。"""
    if not target or ":" not in target:
        logger.warning(
            "InProcessAdapter: skill %r target=%r missing ':' separator (expect 'module:func')",
            skill_id,
            target,
        )
        return None
    module_path, _, func_name = target.partition(":")
    module_path = module_path.strip()
    func_name = func_name.strip()
    if not module_path or not func_name:
        logger.warning(
            "InProcessAdapter: skill %r target=%r has empty module/func part",
            skill_id,
            target,
        )
        return None

    try:
        module = importlib.import_module(module_path)
    except Exception as e:
        logger.warning(
            "InProcessAdapter: skill %r failed to import %r: %s",
            skill_id,
            module_path,
            e,
        )
        return None

    fn = getattr(module, func_name, None)
    if fn is None:
        logger.warning(
            "InProcessAdapter: skill %r function %r not found in module %r",
            skill_id,
            func_name,
            module_path,
        )
        return None
    if not callable(fn):
        logger.warning(
            "InProcessAdapter: skill %r %s.%s is not callable",
            skill_id,
            module_path,
            func_name,
        )
        return None
    return fn

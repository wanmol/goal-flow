"""仓库内未 pip 安装的包路径引导（独立模块，避免 import tool 触发循环依赖）。"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
_SRC_ROOT = _PROJECT_ROOT / "src"
_BOOTSTRAPPED = False


def ensure_project_paths() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    # src/ holds both the goalflow package and the vendored agent_kit package.
    for path in (_SRC_ROOT, _PROJECT_ROOT):
        entry = str(path)
        if entry not in sys.path:
            sys.path.insert(0, entry)
    _BOOTSTRAPPED = True

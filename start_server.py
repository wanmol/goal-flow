#!/usr/bin/env python3
"""
启动脚本 for goalflow Web Service
"""

import sys
import os
import uvicorn
from pathlib import Path

# 添加 src/ 到 Python 路径，使 goalflow 包可导入（未 pip install 时）
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

def main():
    """启动web服务"""
    # Windows 控制台默认 GBK,重配置为 UTF-8 以便打印 emoji / 中文
    for stream in (sys.stdout, sys.stderr):
        reconfig = getattr(stream, "reconfigure", None)
        if reconfig:
            try:
                reconfig(encoding="utf-8")
            except Exception:
                pass

    print("🚀 启动 goalflow Web Service...")
    print(f"📁 项目目录: {project_root}")
    print("🌐 服务地址: http://localhost:8000")
    print("-" * 50)
    
    try:
        uvicorn.run(
            "goalflow.app:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info",
            access_log=True
        )
    except KeyboardInterrupt:
        print("\n⏹️  服务已停止")
    except Exception as e:
        print(f"❌ 服务启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

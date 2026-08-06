---
name: code_interpreter
description: 在隔离沙盒中执行 Python 代码，用于数据分析、数值计算、格式转换、图表数据生成等需要真正运行代码才能得出结果的任务。
version: 1.0.0
author: agent_kit
mode: executable
tags:
  - code
  - data-analysis
  - calculation
triggers:
  - 数据分析
  - 统计计算
  - 数值计算
  - 格式转换
  - 执行代码
entry_point:
  kind: in_process
  target: agent_kit.skills.builtin.code_interpreter.scripts.run:run_python_code
  tool_name: run_python_code
enabled: true
---

# code_interpreter

通过远端 dify-sandbox 服务执行 Python 代码并返回 stdout。

适用场景：
- 数据分析与统计计算（pandas / numpy）
- 数值计算与复杂公式（涉及循环、条件、多步骤）
- 格式转换（JSON 解析、数据整理）
- 图表数据生成（只输出数据，不出图）
- 任何需要执行代码才能得出结果的任务

约束：
- 必须用 `print()` 输出最终结果，否则看不到返回。
- 禁止使用绘图库（matplotlib / seaborn / plotly 等），如需图表请只输出数据由上层渲染。
- 无文件系统 / 网络持久化保证。

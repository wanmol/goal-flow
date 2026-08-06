[English](skills.md) | **简体中文**

# 技能（Skills）

技能是以 Markdown 编写的可复用能力，会 **与用户查询进行匹配**，并按需 **注入到系统提示词中**。它们实现了“渐进式披露（progressive disclosure）”：只有当查询确实需要某个技能时，LLM 才会看到它的完整指令。

本仓库中存在两套技能系统：

- **`src/goalflow/skill/`**（主项目）—— 一套供工作流层使用的提示词注入技能引擎。
- **`src/agent_kit/skills/`** —— 智能体 SDK 的技能系统，它额外支持 *可执行* 技能。相关内容见 [agent-kit.md](agent-kit.md#skills)。

本页介绍主项目的引擎。

## 一个技能的构成

一个技能是 `skills/` 下的一个目录，其中包含一个 `SKILL.md` 和一个可选的 `scripts/` 文件夹：

```
skills/
  weather_query/
    SKILL.md
    scripts/
      weather_api.py       # optional; passive in the main-project engine
  product_search/
    SKILL.md
```

`SKILL.md` 由 YAML frontmatter + Markdown 正文组成：

```markdown
---
name: 天气查询
description: 查询指定城市的实时天气信息，包括温度、湿度、风力等
version: 1.0.0
author: your-name
tags: [weather, query]
triggers: [天气, 气温, weather]
enabled: true
---

## 概述
这个技能用于查询天气...

## 使用指南
1. ...

## 示例对话
用户：北京今天天气怎么样？
...

## 限制
- ...
```

Frontmatter 字段（解析为 `SkillMetadata`，`src/goalflow/skill/models.py`）：

| 字段 | 是否必需 | 默认值 | 说明 |
|-------|----------|---------|-------|
| `name` | 是 | — | 显示名称 |
| `description` | 是 | — | 供匹配器判断相关性 |
| `version` | 否 | `"1.0.0"` | |
| `author` | 否 | — | |
| `tags` | 否 | `[]` | |
| `triggers` | 否 | `[]` | |
| `enabled` | 否 | `true` | 被禁用的技能会被跳过 |

`skill_id` **不在** 文件中——它由目录名派生而来。如果存在 `scripts/`，其路径会被记录在 `SkillMetadata.scripts_dir` 上，但主项目引擎将脚本视为被动附件（并不执行它们；agent-kit 引擎才会执行）。

## 流水线

由 `SkillOrchestrator`（`src/goalflow/skill/orchestrator.py`）编排；通过 `SkillOrchestrator.create_default()` 构造。

```
query ─► [match] ─► [load bodies] ─► [inject into prompt] ─► augmented system prompt
```

1. **加载 / 注册** —— `SkillRegistry`（`src/goalflow/skill/registry.py`）扫描 `skills/` 目录（默认 `project_root/skills`），解析每个 `SKILL.md`，校验必填字段，并以 `skill_id` 为键缓存 `SkillMetadata`。支持通过 mtime 跟踪实现热重载（`scan()`、`reload()`、`has_changes()`）。

2. **匹配** —— `SkillMatcher`（`src/goalflow/skill/matcher.py`）是 **基于 LLM 的**，而非关键词匹配。它将一段匹配提示词、查询以及一个 `{skill_id, name, description}` 的 JSON 列表发送给 LLM（默认 `qwen` / `qwen-turbo`，温度 0.1，可通过 `SKILL_MATCH_PROVIDER` / `SKILL_MATCH_MODEL` 覆盖）。它解析出 `MatchResult` 对象 `{skill_id, skill_name, confidence, reason}`，按 `threshold`（默认 0.3）过滤，按置信度排序，并截断到 `top_k`（默认 1）。

3. **加载正文** —— `SkillLoader`（`src/goalflow/skill/loader.py`）读取匹配到的文件，并将 Markdown 正文（frontmatter 之后的全部内容）作为 `SkillContent` 返回。

4. **注入** —— `SystemPromptBuilder`（`src/goalflow/skill/prompt_builder.py`）在基础提示词后追加一个 `## 当前激活的技能详情` 小节，将每个匹配到的技能的完整正文放在 `### {name} (v{version})` 之下。

一次调用的便捷方式：

```python
orchestrator = SkillOrchestrator.create_default()
augmented_prompt = orchestrator.build_prompt(
    query=user_query,
    base_prompt=system_prompt,
    top_k=1,
    threshold=0.3,
)
```

## 编写技巧

- **`description` 最为关键** —— 它是匹配器进行推理所依据的内容。要具体说明技能 *何时* 适用。
- **保持正文聚焦** —— 它们会被逐字注入到提示词中，因而会消耗上下文。放入使用规则、示例和限制；剔除模型并不需要的赘述。
- **使用 `enabled: false`** 可以让一个技能留在仓库中而不被激活。
- **`triggers`/`tags`** 是给人看的元数据、以及未来关键词兜底所用；当前的匹配器由 LLM 驱动。

## 调优匹配器

| 环境变量 | 作用 |
|---------|--------|
| `SKILL_MATCH_PROVIDER` | 用于匹配的 LLM 提供方（默认 `qwen`） |
| `SKILL_MATCH_MODEL` | 模型（默认 `qwen-turbo`） |

`threshold` 和 `top_k` 是 `match()` / `build_prompt()` 的参数。提高 `top_k` 可一次激活多个技能；提高 `threshold` 可更加严格地筛选。

## 何时使用主项目技能 vs. agent-kit 技能

- 当你想用匹配到的指令来丰富某个工作流 LLM 节点的提示词时，使用 **`src/goalflow/skill/`**。
- 当你想要既能在智能体循环中 *作为工具执行* 的技能（prompt-only、可执行的 `module:func`，或混合模式）时，使用 **`agent_kit` 技能**。参见 [agent-kit.md](agent-kit.md#skills)。

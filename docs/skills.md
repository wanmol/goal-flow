**English** | [简体中文](skills.zh-CN.md)

# Skills

Skills are reusable, Markdown-authored capabilities that get **matched to a user query** and **injected into the system prompt** on demand. They implement "progressive disclosure": the LLM sees a skill's full instructions only when the query actually calls for it.

There are two skill systems in this repository:

- **`src/goalflow/skill/`** (main project) — a prompt-injection skill engine used by the workflow layer.
- **`src/agent_kit/skills/`** — the agent SDK's skill system, which additionally supports *executable* skills. Covered in [agent-kit.md](agent-kit.md#skills).

This page documents the main-project engine.

## Anatomy of a skill

A skill is a directory under `skills/` containing a `SKILL.md` and an optional `scripts/` folder:

```
skills/
  weather_query/
    SKILL.md
    scripts/
      weather_api.py       # optional; passive in the main-project engine
  product_search/
    SKILL.md
```

`SKILL.md` is YAML frontmatter + a Markdown body:

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

Frontmatter fields (parsed into `SkillMetadata`, `src/goalflow/skill/models.py`):

| Field | Required | Default | Notes |
|-------|----------|---------|-------|
| `name` | yes | — | display name |
| `description` | yes | — | used by the matcher to judge relevance |
| `version` | no | `"1.0.0"` | |
| `author` | no | — | |
| `tags` | no | `[]` | |
| `triggers` | no | `[]` | |
| `enabled` | no | `true` | disabled skills are skipped |

`skill_id` is **not** in the file — it's derived from the directory name. If `scripts/` exists its path is recorded on `SkillMetadata.scripts_dir`, but the main-project engine treats scripts as passive attachments (it doesn't execute them; the agent-kit engine does).

## The pipeline

Orchestrated by `SkillOrchestrator` (`src/goalflow/skill/orchestrator.py`); construct with `SkillOrchestrator.create_default()`.

```
query ─► [match] ─► [load bodies] ─► [inject into prompt] ─► augmented system prompt
```

1. **Load / register** — `SkillRegistry` (`src/goalflow/skill/registry.py`) scans the `skills/` directory (default `project_root/skills`), parses each `SKILL.md`, validates required fields, and caches `SkillMetadata` keyed by `skill_id`. Supports hot reload via mtime tracking (`scan()`, `reload()`, `has_changes()`).

2. **Match** — `SkillMatcher` (`src/goalflow/skill/matcher.py`) is **LLM-based**, not keyword matching. It sends a match prompt plus the query and a JSON list of `{skill_id, name, description}` to an LLM (default `qwen` / `qwen-turbo`, temp 0.1, overridable via `SKILL_MATCH_PROVIDER` / `SKILL_MATCH_MODEL`). It parses `MatchResult` objects `{skill_id, skill_name, confidence, reason}`, filters by `threshold` (default 0.3), sorts by confidence, and truncates to `top_k` (default 1).

3. **Load bodies** — `SkillLoader` (`src/goalflow/skill/loader.py`) reads the matched files and returns the Markdown body (everything after the frontmatter) as `SkillContent`.

4. **Inject** — `SystemPromptBuilder` (`src/goalflow/skill/prompt_builder.py`) appends a `## 当前激活的技能详情` section to the base prompt, with each matched skill's full body under `### {name} (v{version})`.

One-call convenience:

```python
orchestrator = SkillOrchestrator.create_default()
augmented_prompt = orchestrator.build_prompt(
    query=user_query,
    base_prompt=system_prompt,
    top_k=1,
    threshold=0.3,
)
```

## Authoring tips

- **`description` matters most** — it's what the matcher reasons over. Make it specific about *when* the skill applies.
- **Keep bodies focused** — they're injected verbatim into the prompt, so they consume context. Put usage rules, examples, and limits; leave out prose the model doesn't need.
- **Use `enabled: false`** to keep a skill in the repo without activating it.
- **`triggers`/`tags`** are metadata for humans and future keyword fallbacks; the current matcher is LLM-driven.

## Tuning the matcher

| Env var | Effect |
|---------|--------|
| `SKILL_MATCH_PROVIDER` | LLM provider for matching (default `qwen`) |
| `SKILL_MATCH_MODEL` | model (default `qwen-turbo`) |

`threshold` and `top_k` are arguments to `match()` / `build_prompt()`. Raise `top_k` to activate multiple skills at once; raise `threshold` to be more selective.

## When to use main-project skills vs. agent-kit skills

- Use **`src/goalflow/skill/`** when you want to enrich a workflow LLM node's prompt with matched instructions.
- Use **`agent_kit` skills** when you want skills that can also be *executed as tools* inside an agent loop (prompt-only, executable `module:func`, or hybrid). See [agent-kit.md](agent-kit.md#skills).

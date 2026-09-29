# A股推荐 Skill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 创建一个能用项目 a-stock-data 数据筛选三个标准首板 1进2候选的项目内 Codex Skill。

**Architecture:** Skill 负责工作流、边界与输出约束；确定性 Python 脚本负责候选资格、基础评分和组合约束；详细规则放在 reference 中。模型只能解释脚本返回的数据，并用真实公开信息进行确认或否决。

**Tech Stack:** Codex Skills、Python 3.10+、项目 `vr/astock.py` / `vr/market.py`、pytest。

---

### Task 1: 创建 Skill 接口与策略规范

**Files:**
- Create: `.codex/skills/a-share-recommendation/SKILL.md`
- Create: `.codex/skills/a-share-recommendation/agents/openai.yaml`
- Create: `.codex/skills/a-share-recommendation/references/strategy-spec.md`

**Steps:**
1. 写明只做真实首板次日 1进2、40元价格约束及三只输出格式。
2. 写明 a-stock-data 数据源、信息缺失降级和次日确认闸门。
3. 保持默认自动发现，并配置中文显示名“A股推荐 Skill”。

### Task 2: 实现确定性首板筛选

**Files:**
- Create: `.codex/skills/a-share-recommendation/scripts/rank_first_boards.py`
- Create: `tests/test_a_share_recommendation.py`

**Steps:**
1. 先写测试覆盖真实首板识别、反包排除、价格限制和跨板块组合。
2. 运行测试并确认失败。
3. 实现纯函数筛选、评分和三只组合。
4. 增加 `--live`，复用项目 `vr` 数据层输出 JSON。
5. 运行测试并确认通过。

### Task 3: 验证 Skill 与今日数据

**Files:**
- Verify: `.codex/skills/a-share-recommendation/`

**Steps:**
1. 使用 `quick_validate.py` 验证 Skill 结构与 frontmatter。
2. 对 2026-09-16 收盘池运行脚本。
3. 核对输出均为沪深主板、1天1板、价格严格低于40元且至少两个板块。
4. 用真实资讯与公告完成三只候选的解释和风险降级。

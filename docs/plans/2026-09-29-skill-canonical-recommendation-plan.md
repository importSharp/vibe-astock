# Skill Canonical Recommendation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use the Code execution workflow to implement this plan task-by-task.

**Goal:** Make the website and Codex A-share recommendation skill consume the same immutable post-market result, generated no earlier than 15:35 China time.

**Architecture:** The skill ranker remains the only scoring engine. It exposes a canonical snapshot reader that attaches a deterministic rules fingerprint and candidate fingerprint. The website calls that canonical reader instead of independently interpreting snapshot JSON, while the skill CLI uses canonical mode for user-facing recommendations and reserves live recomputation for diagnostics.

**Tech Stack:** Python 3, FastAPI, pytest, JSON snapshots, SHA-256 fingerprints.

---

### Task 1: Define the canonical skill contract

**Files:**
- Modify: `.codex/skills/a-share-recommendation/scripts/rank_first_boards.py`
- Test: `tests/test_a_share_recommendation_skill.py`

**Steps:**
1. Add failing tests for deterministic rule and candidate fingerprints.
2. Add a canonical snapshot loader that reads an existing immutable snapshot and never silently recomputes historical recommendations.
3. Add a `--canonical` CLI mode and keep `--live` as an explicit diagnostic mode.
4. Change official snapshot eligibility from 15:05 to 15:35.
5. Run focused ranker tests.

### Task 2: Make the website consume the canonical contract

**Files:**
- Modify: `duanxian/recommendation.py`
- Modify: `server.py`
- Test: `tests/test_two_stage_recommendation.py`

**Steps:**
1. Add failing tests that website output contains the same strategy and candidate fingerprints as the skill snapshot.
2. Route the post-market endpoint through the ranker's canonical snapshot reader.
3. Expose canonical source metadata from the endpoint.
4. Move the automatic generation window to 15:35–15:50.
5. Run the two-stage recommendation tests.

### Task 3: Update skill instructions and verify the full contract

**Files:**
- Modify: `.codex/skills/a-share-recommendation/SKILL.md`
- Modify: `.codex/skills/a-share-recommendation/references/strategy-spec.md`
- Modify: `docs/plans/2026-09-29-two-stage-recommendation-design.md`
- Test: `tests/test_two_stage_recommendation.py`

**Steps:**
1. Document `--canonical` as the required Codex command and `--live` as diagnostics only.
2. Document 15:35 as the official snapshot time.
3. Validate the skill package with the bundled skill validator.
4. Run focused tests, then the full test suite.
5. Query the running website endpoint and compare its fingerprints and candidates with canonical CLI output.

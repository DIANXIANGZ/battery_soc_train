# GitHub Baseline Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a clean local Git baseline for the SOC battery project and connect it to the empty GitHub repository without pushing or creating a PR.

**Architecture:** Keep source code, tests, configuration templates, and reviewable documentation in the repository. Exclude local data, generated results, caches, temporary evidence, and the oversized audit CSV through a root `.gitignore`. Initialize Git on the confirmed project root, add the GitHub HTTPS remote, review the exact staged file list, and create one local baseline commit.

**Tech Stack:** Git, Python 3.12 project, pytest configuration in `pyproject.toml`.

## Global Constraints

- Work only in `/Users/wanghaoming/Public/battery_soc_project/battery_soc_project`.
- Do not modify source code, datasets, `configs/paths.json`, or existing documentation content.
- Do not push to GitHub and do not create a pull request in this task.
- Do not add the 265 MB audit CSV, local data, generated results, caches, or `tmp/`.
- Preserve the existing project structure and review the staged list before committing.

---

### Task 1: Establish repository exclusions

**Files:**
- Create: `.gitignore`
- Create: `docs/superpowers/plans/2026-08-10-github-baseline.md`

- [x] **Step 1: Inspect repository contents and identify exclusions**

Confirmed exclusions are Python/macOS caches, local environments, `data/`, `results/`, `artifacts/`, `outputs/`, `tmp/`, and `docs/audits/v10_phase12_pretraining/soc_soe_physics_rows.csv`.

- [ ] **Step 2: Verify ignore rules**

Run `git check-ignore -v tmp/ docs/audits/v10_phase12_pretraining/soc_soe_physics_rows.csv src/__pycache__/x.pyc` after Git initialization. Each path must be ignored by the intended rule.

### Task 2: Initialize and connect Git

**Files:**
- Create: `.git/` (Git metadata only)

- [ ] **Step 1: Initialize the repository**

Run `git init -b main` in the confirmed project root.

- [ ] **Step 2: Add the remote**

Run `git remote add origin https://github.com/DIANXIANGZ/battery_soc_train.git` and verify with `git remote -v`.

### Task 3: Create a reviewed local baseline

**Files:**
- Add only files not excluded by `.gitignore`.

- [ ] **Step 1: Review staged candidates**

Run `git add -A`, then inspect `git status --short`, `git diff --cached --stat`, and `git diff --cached --name-only`.

- [ ] **Step 2: Confirm prohibited files are absent**

Run `git diff --cached --name-only | rg '(^|/)(tmp|data|results|artifacts|outputs|__pycache__)/|soc_soe_physics_rows\.csv$'`. Expected: no output.

- [ ] **Step 3: Create the local baseline commit**

Run `git commit -m "chore: establish SOC battery project baseline"` only after the staged list is clean.

### Task 4: Verify handoff state

**Files:**
- No additional files.

- [ ] **Step 1: Verify repository state**

Run `git status --short --branch`, `git log -1 --oneline`, and `git remote -v`. Expected: clean `main` branch, one local baseline commit, and the requested `origin` URL.

- [ ] **Step 2: Verify no push occurred**

Run `git branch -vv` and report that the baseline remains local until the user explicitly requests a push.

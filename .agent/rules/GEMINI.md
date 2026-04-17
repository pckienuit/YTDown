---
trigger: always_on
---

---
trigger: always_on
description: Core behavioral guidelines, agent routing, and Antigravity workspace protocols.
---

# SYSTEM PROTOCOL - Antigravity Kit

> This file defines the core behavioral guidelines and operational protocols for the AI in this workspace. It merges strict architectural instructions with behavioral rules designed to reduce common coding mistakes.
>
> **Core Tradeoff:** These guidelines bias toward **caution and simplicity over speed**. For trivial tasks, use judgment, but never at the expense of system integrity.

---

## 🛑 CRITICAL: AGENT & SKILL PROTOCOL (START HERE)

> **MANDATORY:** You MUST read the appropriate agent file and its skills BEFORE performing any implementation. This is the highest priority rule.

### 1. Modular Skill Loading Protocol
Agent activated -> Check frontmatter `skills:` -> Read `SKILL.md` (INDEX) -> Read specific sections.
- **Selective Reading:** DO NOT read ALL files in a skill folder. Read `SKILL.md` first, then only read sections matching the user's request.
- **Rule Priority:** P0 (SYSTEM PROTOCOL) > P1 (Agent `.md`) > P2 (`SKILL.md`). All rules are binding.

### 2. Enforcement Protocol
1. **Activate:** Read Rules -> Check Frontmatter -> Load `SKILL.md` -> Apply All.
2. **Read -> Understand -> Apply:** 
   * ❌ *WRONG:* Read agent file -> Start coding immediately.
   * ✅ *CORRECT:* Read -> Understand WHY -> Apply PRINCIPLES -> Code.
3. **Forbidden:** Never skip reading agent rules or skill instructions. 

---

## 🔬 TIER 0.5: GRAPUCO CODE INTELLIGENCE (Mandatory Before Edits)

> **MCP:** `grapuco` — Graph-based code analysis. Skill: `@[skills/grapuco-code-intel]`

### When to activate Grapuco

| Scenario | Tool | Skill |
| :--- | :--- | :--- |
| Sửa function/class bất kỳ | `blast_radius` | `safe-edit` |
| Debug bug / stack trace | `get_symbol_context` + `blast_radius` | `investigate-bug` |
| Rename symbol | `rename_symbol` (dryRun:true → false) | `rename-symbol` |
| Trước khi commit | `detect_changes` + git diff | `pre-commit-check` |
| Lên kế hoạch refactor | `blast_radius` + `get_symbol_context` | `plan-refactor` |
| Onboard repo mới | `get_architecture` + `semantic_search` | `explore-codebase` |
| Trace API → DB | `get_data_flows` + `get_symbol_context` | `trace-request` |

### MANDATORY Protocol
1. **Trước khi sửa ANY function/class:** Chạy `blast_radius` → đọc `riskLevel`
2. **riskLevel HIGH/CRITICAL:** DỪNG → lên kế hoạch incremental → xác nhận với user
3. **Rename bất kỳ symbol:** LUÔN dùng `rename_symbol { dryRun: true }` trước
4. **Trước commit:** Chạy `detect_changes` với output của `git diff HEAD`
5. **Session mới trên repo chưa quen:** Gọi `bootstrap` + `list_repositories` trước

> ⚠️ `get_context` tốn **5 AI credits** — chỉ dùng khi `semantic_search` không đủ.

---

## 🧠 TIER 0: CORE BEHAVIORAL PRINCIPLES (Always Active)

### 1. Think Before Coding & The Socratic Gate
**Don't assume. Don't hide confusion. Surface tradeoffs.**
**MANDATORY:** Every user request must pass through the **Socratic Gate** before ANY tool use or implementation.

| Request Type | Strategy | Required Action |
| :--- | :--- | :--- |
| **New Feature/Build** | Deep Discovery | ASK minimum 3 strategic questions |
| **Code Edit/Bug Fix** | Context Check | Confirm understanding + ask impact questions |
| **Vague/Simple** | Clarification | Ask Purpose, Users, and Scope |
| **Full Orchestration**| Gatekeeper | **STOP** subagents until user confirms plan details |
| **Direct "Proceed"** | Validation | **STOP** -> Even if given answers, ask 2 "Edge Case" questions |

- **State assumptions explicitly.** If multiple interpretations exist, present them - don't pick silently.
- **Handle Spec-heavy Requests:** Ask about **Trade-offs** or **Edge Cases** before starting.
- **Push back:** If a simpler approach exists, say so. If something is unclear, stop, name what's confusing, and ask.

### 2. Simplicity First & Clean Code
**Minimum code that solves the problem. Nothing speculative.**
- **No extra features:** No features, abstractions, "flexibility", or "configurability" beyond what was explicitly asked.
- **No over-engineering:** No error handling for impossible scenarios. If you write 200 lines and it could be 50, rewrite it.
- **Clean Code Mandatory:** All code MUST follow `@[skills/clean-code]`. Self-documenting, concise.
- **Testing & Perf:** Pyramid Testing (Unit > Int > E2E) + AAA Pattern. Measure performance first (Core Web Vitals). 5-Phase Deployment. Verify secrets security.

*Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.*

### 3. Surgical Changes & Dependency Awareness
**Touch only what you must. Clean up only your own mess.**
- **Dependency Check (Grapuco-first):** Before modifying ANY symbol, run `blast_radius` (MCP grapuco). If no Grapuco data: check `CODEBASE.md` -> File Dependencies -> Update ALL affected files together.
- **Editing Rules:** Don't "improve" adjacent code, comments, or formatting. Match existing style. Don't refactor unbroken things.
- **Orphan Cleanup:** Remove imports/variables/functions that YOUR changes made unused. Do NOT remove pre-existing dead code unless asked (mention it instead).

*The test: Every changed line should trace directly to the user's request.*

### 4. Goal-Driven Execution
**Define success criteria. Loop until verified.**
Transform tasks into verifiable goals (e.g., "Fix the bug" → "Write a test that reproduces it, then make it pass", "Refactor X" → "Ensure tests pass before and after"). Strong success criteria let you loop independently.

For multi-step tasks, state a brief plan:
```text
1. [Step] → verify: [check]
2. [Step] → verify: [check]
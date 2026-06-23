---
name: quick-implement
description: Session-based ad-hoc task execution with per-task extension hooks (LOW-FRICTION
  MODE)
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: agentic-quick:commands/adlc.quick.implement.md
disable-model-invocation: false
---

## Quick: Low-Friction Session-Based Task Execution

**Design Principles**: Minimal stops (Mission Brief only). Per-task extension hooks. Auto-proceed. Hooks fire on errors.

---

## User Input

```text
$ARGUMENTS
```

Consider the user input before proceeding (if not empty).

---

## ⚠️ MANDATORY STOP: Mission Brief

Collect answers to:

1. What needs to be done? (primary task/feature/fix)
2. What defines success? (completion criteria)
3. Any constraints? (time, priority, dependencies, tech limits)

Display:

```markdown
## Mission Brief

**Goal**: {response 1}
**Success Criteria**: {response 2}
**Constraints**: {response 3}
```

**STOP** — Wait for explicit "yes".
- **no**: Ask what to adjust, re-display, ask again.
- **yes**: Proceed to execution.

---

## Pre-Execution Hooks

**STOP. Before reading User Input or doing ANY other work, execute extension hooks.**

1. If `{REPO_ROOT}/.specify/extensions.yml` does not exist, state `No hooks file found` and skip to User Input.
2. Read `{REPO_ROOT}/.specify/extensions.yml` and find `hooks.before_implement`.
3. Skip any hook with `enabled: false`. Skip any hook with a non-empty `condition`.
4. For each remaining hook:
   - **Mandatory** (`optional: false`): Read the command file for `{command}`. **First, read the extension's `extension.yml` manifest** and look up the `provides.commands` entry matching `{command}` to get the `file` field. Use that `file` path relative to the extension directory. If the manifest cannot be read, fall back to looking for `{command}.md` directly in the extension commands directory. Execute the command file's full instructions NOW before continuing.
   - **Optional** (`optional: true`): Display the hook name, command, and description. Let the user decide.
5. State which hooks were executed, then proceed to User Input.

---

## Context Discovery (Auto)

After Mission Brief approved, ask briefly:

```markdown
## Context

Any specific files to examine? (optional)
```

Wait briefly, then proceed (can be empty).

---

## Constitution Alignment (Auto)

**IF EXISTS**: Load `{REPO_ROOT}/.specify/memory/constitution.md` for project principles and governance constraints.

---

## Task Breakdown (Auto)

Generate and display:

```markdown
## Task Breakdown

- [ ] {Task 1}
- [ ] {Task 2}
- [ ] {Task 3}
```

**Do not ask for approval** — proceed directly to execution.

---

## Execution: Per-Task Hook Dispatch

### For Each Task (IN ORDER):

1. **Display task**: `## Task {N}: {description}`

2. **Dispatch `before_task_execute` hooks**:
   - Read `{REPO_ROOT}/.specify/extensions.yml`, locate `hooks.before_task_execute`
   - Skip `enabled: false` and non-empty `condition`
   - **Mandatory**: Resolve command file via manifest (`provides.commands.{command}.file`), fallback to `{command}.md`. Execute immediately.
   - **Optional**: Skip silently (maintain low-friction flow)
   - If no hooks or file missing, continue silently

3. **Execute**: Read files if needed, make changes

4. **Dispatch `after_task_execute` hooks**:
   - Same logic as `before_task_execute`

5. **Auto-proceed** to next task (no pause)

### After All Tasks Complete

Display summary:

```markdown
## Quick Implementation Complete

**Tasks completed**:
- [x] Task 1: ...
- [x] Task 2: ...

**Files modified**: {count}
**Next steps**: {optional}
```

---

## Post-Execution Hooks

1. If `{REPO_ROOT}/.specify/extensions.yml` does not exist, skip silently.
2. Read `hooks.after_implement`.
3. Skip hooks with `enabled: false` or non-empty `condition`.
4. For each remaining hook:
   - **Mandatory** (`optional: false`): Read the command file for `{command}`. **First, read the extension's `extension.yml` manifest** and look up the `provides.commands` entry matching `{command}` to get the `file` field. Use that `file` path relative to the extension directory. If the manifest cannot be read, fall back to looking for `{command}.md` directly in the extension commands directory. Execute the command file's full instructions immediately.
   - **Optional** (`optional: true`): Display hook info for user decision.
5. If no hooks registered, skip silently.

---

## Error Handling

If a task fails:

1. **Dispatch `after_task_execute` hooks** (same logic as above — allows WIP checkpoint if git extension is configured)

2. **Display error**:

   ```markdown
   **Task Failed**: {task description}

   Error: {error message}

   What would you like to do?
   - (1) Retry this task
   - (2) Skip to next task
   - (3) Stop execution
   ```

3. **Wait for user decision** — do not auto-retry or auto-skip

---

## Critical Constraints

1. **1 stop only** — Mission Brief confirmation is the only interactive stop
2. **Per-task hooks** — `before_task_execute` / `after_task_execute` dispatch around each task
3. **No pauses between tasks** — Auto-proceed after hooks complete
4. **Hooks on error** — `after_task_execute` hooks fire on failure before asking user
5. **No file artifacts** — No PLAN.md, TASKS.md, or other workflow files
6. **Session-only** — All interaction in conversation
7. **Manual final commit** — User decides when to push/merge

---

## Per-Task Commit Messages

When the git extension is installed with `after_task_execute.enabled: true`, the commit message is controlled by `auto_commit.after_task_execute.message` in `.specify/extensions/git/git-config.yml`.

Example:

```yaml
auto_commit:
  after_task_execute:
    enabled: true
    message: "[quick] Task checkpoint"
```

Produces commits like: `[quick] Task 1: Add error handling to login API`

---

## Output Notes

- Task execution happens in actual codebase
- No workflow/documentation files created
- Per-task commits provide checkpoint history (when git extension is configured)
- User can `git reset` to any task if needed
- User manages final push/merge manually
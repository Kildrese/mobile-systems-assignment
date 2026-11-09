# Tasks

## 1. Rules

- [x] 1.1 `CLAUDE.md`: add the Decisions section (classes, the `mine` list from D2, entry format) and one Workflow line for `claude --agent orchestrator`

## 2. Agents

- [x] 2.1 `.claude/agents/orchestrator.md` from trademark: the loop in design.md, checker/security-reviewer instead of check.sh/db-agent, draft PR then `/ship`, Sonnet rule for this repo, frontmatter hook on Edit|Write
- [x] 2.2 `.claude/agents/spec-writer.md` (preloads `openspec-ff-change`; no DESIGN.md)
- [x] 2.3 `.claude/agents/implementer.md` (CLAUDE.md's commands instead of check.sh; local `alembic` allowed, production never)
- [x] 2.4 `.claude/agents/reviewer.md`: add Pass 3 (decisions) and its output section

## 3. Hook

- [x] 3.1 `.claude/hooks/orchestrator-writes.sh`
- [x] 3.2 `.claude/hooks/test-orchestrator-writes.sh` covering the four scenarios in the spec; it passes

## 4. Check

- [ ] 4.1 First real orchestrator run on a small feature: `decisions.md` gets grilling entries with `landed:`, an implementer stops on a `mine` choice, the reviewer runs Pass 3. Note what broke in this change's `decisions.md`.

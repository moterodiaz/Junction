# Development tooling evidence: Codex and Entire (DEV-D1, #137)

Requirement: REQ-DEV-01. PRD §12.11. Owner: Mateo (@moterodiaz, lead).

**Status: both tracks stay candidate.** No commit on `main` is attributed to Codex, and no Entire checkpoint, handoff or codebase-graph workflow has run. The only Codex-related artifacts in the repo are its configuration (`.agents/`, including the `safety-gate.py` hook), and having configuration is not a contribution.

## 1. Contribution map from commit attribution

`git log origin/main` at `9d10e28` (2026-11-15): 124 commits from 2026-11-13 to 2026-11-15. A commit counts for a tool when its `Co-authored-by` trailers name that tool, so a commit can count for several.

| Tool (trailer) | Commits |
|---|---|
| Claude Sonnet (`Claude Sonnet …`) | 67 |
| `claude[bot]` (the `claude-fix` workflow and Claude GitHub app) | 54 |
| `factory-droid[bot]` (Factory Droid) | 28 |
| Claude Opus (`Claude Opus …`) | 24 |
| Cursor (`cursoragent@cursor.com`) | 2 |
| **Codex / OpenAI** | **0** |
| No tool trailer | 17 |

The scan matched `Codex`, `codex` and `OpenAI` in trailers; `git log --grep=codex -i` found no commit message either.

Limits of this map:
- Attribution relies on trailers the tools add. The 17 commits without a trailer could come from any tool or from a person. Nothing proves either.
- Per-file and per-test attribution was not done. With 0 Codex commits there is nothing to map.

## 2. Entire

No Entire CLI is installed on the lead's machine, and none appears in the repo. A real workflow needs three things, none of which exist yet:
1. The lead's approval to install it. Installs need his explicit OK.
2. A purpose-built, cleared development session. We never upload existing transcripts.
3. Recorded checkpoint, handoff and graph observations, with what a human reviewed.

## 3. What would move each track out of candidate

- **Codex:** a real task done with Codex, committed with a Codex trailer and reviewed through the normal PR flow. Then it gets a row here with its commit, files and tests.
- **Entire:** steps 1 to 3 above, with measured observations and limits.

Neither is started by this file.

## Reproduce

```
git log origin/main --format='%H %(trailers:key=Co-authored-by,valueonly,separator=;) %an' | grep -c '<tool>'
git log origin/main -i --grep=codex --oneline
```

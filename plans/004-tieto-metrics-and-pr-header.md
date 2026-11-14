# Plan 004: Trust is measured by a script and shown on every PR as a self-explaining header

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 6491a8f..HEAD -- tools/ .github/workflows/ docs/REQUIREMENTS.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M (half a day)
- **Risk**: MED — a new workflow posts comments on PRs; a bug spams or blocks PRs. Mitigated by one sticky comment per PR and a dry-run step.
- **Depends on**: plans/003-tieto-deliverables-docs.md (needs `docs/REQUIREMENTS.md` and the REQ-id convention)
- **Category**: dx
- **Planned at**: commit `6491a8f`, 2026-11-14

## Why this matters

Two of the four Tieto rubric items are about **measurement (25%)** and
**evidence (20%)**. Today nothing in the repo measures the pipeline, and no PR
shows what the AI verified, what it refused, or who signed off. The data exists
in GitHub (review threads, fixer commits, `needs human` comments, merge times);
it just has to be computed and surfaced. One script (`tools/metrics`) and one
small workflow (`pr-header.yml`) turn the existing pipeline into a judged
deliverable: a live walkthrough on a real PR with the three required blocks and
a metrics panel.

A gotcha this plan must respect: `gh pr list --json ...,commits --limit 100`
hits GitHub's GraphQL node limit ("requesting up to 1,000,000 possible nodes
which exceeds the maximum limit of 500,000") — this is exactly what has been
breaking `pr-sweeper.yml` all day. Never request `commits` in `gh pr list`; use
the REST commits endpoint per PR.

## Current state

- `tools/` holds bash scripts `board`, `task`, `wt`, `kickoff`, `onboard`; all start
  with `#!/usr/bin/env bash` and `set -euo pipefail`; they rely only on `gh`, `jq`,
  `git`. `ci.yml` runs `bash -n` over `tools/*`. Model new scripts on `tools/board`
  (argument parsing, `usage` message, `REPO` from `gh repo view`).
- Board posts are comments on issue #1, created with
  `gh api repos/$REPO/issues/1/comments -f body=...` (see `pr-sweeper.yml:45`).
- `.github/workflows/claude-fix.yml:101-133` — the fixer prompt already asks for
  `Fixed in <sha>` replies and `needs human: <reason>` on refused threads. PR
  comments containing `needs human` are the escalation signal; they are posted by
  `github-actions[bot]` (lines 195–198, 214–217, 232–235) and sometimes by humans' agents.
- Branch protection (`gh api repos/moterodiaz/Junction/rules/branches/main`):
  required status checks `ci` and `Greptile Review`; adding a new required check
  is a human action in GitHub settings.
- No `CODEOWNERS`; owners live in `AGENTS.md` section 4:
  `ios/` → `@maksymmatviievskyi`; `backend/app/`, `backend/stt/` → `@Ahm3d-KA`;
  `backend/ai/` → `@Marcus228`; `contracts/` → `@moterodiaz`; `.github/`, `.claude/` → lead `@moterodiaz`.
- Verified `gh`/`jq` fragments (ran successfully on 2026-11-14 against this repo):

  Time to merge and sizes (no `commits` field):
  ```sh
  gh pr list -R "$REPO" --state all --limit 100 \
    --json number,author,createdAt,mergedAt,state,additions,title,body --jq '
    [.[] | select(.number >= 67)] as $prs |
    ($prs | map(select(.state=="MERGED"))) as $m |
    "merged=\($m|length) open=\($prs|map(select(.state=="OPEN"))|length)",
    "ttm_median_min=\([$m[] | ((.mergedAt|fromdateiso8601) - (.createdAt|fromdateiso8601))/60] | sort | .[length/2|floor] | floor)",
    "ttm_mean_min=\(([$m[] | ((.mergedAt|fromdateiso8601) - (.createdAt|fromdateiso8601))/60] | add / length) | floor)",
    "with_req_id=\([$prs[] | select((.title + .body) | test("REQ-[A-Z]+-[0-9]+"))] | length)",
    "reverts=\([$prs[] | select(.title | test("revert";"i"))] | length)"'
  ```
  Fixer commits per PR (REST, paginated):
  ```sh
  gh api --paginate "repos/$REPO/pulls/$n/commits" \
    --jq '[.[] | select(.commit.message | startswith("fix: address greptile review"))] | length' | awk '{s+=$1} END{print s+0}'
  ```
  Review threads with dispositions (GraphQL, per PR):
  ```sh
  gh api graphql -f query="{repository(owner:\"${REPO%/*}\",name:\"${REPO#*/}\"){pullRequest(number:$n){reviewThreads(first:100){nodes{isResolved comments(first:6){nodes{author{login} body}}}}}}}" \
    --jq '.data.repository.pullRequest.reviewThreads.nodes[] | [.isResolved, ([.comments.nodes[1:][] | .body] | join(" | "))] | @tsv'
  ```
  Classify each thread's replies: contains `needs human` → escalated; matches
  `fixed in|addressed|done in|fixed` (case-insensitive) → fixed; matches
  `not changing|not valid|invalid|false positive|by design|intentional|won't|wont` → rejected; else → **silent**.
  `needs human` comments on a PR: `gh pr view $n --json comments --jq '[.comments[].body | select(contains("needs human"))] | length'`.
- Baseline measured at planning time (see plan 003's table): 22 PRs, median 5 min
  to merge, 69 threads / 25 fixed / 0 rejected / 44 silent, 24 fixer commits,
  45 `needs human` board posts, 0 reverts, 0 REQ ids.

## Commands you will need

| Purpose | Command | Expected |
|---|---|---|
| Shell syntax (what ci runs) | `bash -n tools/metrics` | exit 0 |
| Run the script | `tools/metrics` | a markdown table on stdout |
| Run with JSON | `tools/metrics --json` | one JSON object |
| Workflow lint (if installed) | `actionlint .github/workflows/pr-header.yml` | no errors (skip if `actionlint` is missing) |
| Dry-run the header on a PR | `gh workflow run pr-header.yml -f pr_number=<N>` then `gh run watch` | one new/updated comment on PR N |

## Scope

**In scope**:
- `tools/metrics` (create, executable)
- `.github/workflows/pr-header.yml` (create)
- `.github/workflows/claude-fix.yml` (one prompt sentence, Step 4 — optional)
- `docs/TIETO_CONCEPT_CARD.md` (paste the generated table into section 5 — only if plan 003 has landed)

**Out of scope**:
- `pr-sweeper.yml` fixes — plan 007.
- Branch-protection / ruleset changes (human action; note them in the PR body).
- Any product code.

## Git workflow

Follow `AGENTS.md`. Workflow files need **one human merge**: post on the board
tagging `@moterodiaz` when the PR is open. Two PRs are fine: PR A `tools/metrics`
(auto-merge), PR B `.github/workflows/pr-header.yml` (+ the claude-fix prompt
line) — human merge. Titles carry `(REQ-PROC-01)`.
Commit style: `feat(tools): tools/metrics measures the PR pipeline`,
`chore(github): pr-header posts the trust header and REQ check on every PR`.

## Steps

### Step 1: `tools/metrics`

Create `tools/metrics` (chmod +x), bash, `set -euo pipefail`, usage:
`tools/metrics [--since <pr-number>] [--json]` (default `--since 67`, the first
product PR). Implementation outline:

1. `REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"`.
2. Pull the PR list once (the `gh pr list` fragment above; **no `commits`**).
3. For each PR number: fixer commits (REST fragment), review-thread rows
   (GraphQL fragment) classified into `fixed|rejected|escalated|silent`, and
   `needs human` comment count.
4. Compute and print a markdown table with these rows (and the same keys in
   `--json`): `prs_opened`, `prs_merged`, `ttm_median_min`, `ttm_mean_min`,
   `threads_total`, `threads_fixed`, `threads_rejected`, `threads_silent`,
   `disposition_coverage_pct` (= (fixed+rejected)/total), `ai_acceptance_pct`
   (= fixed/(fixed+rejected), print `n/a` when the denominator is 0),
   `fixer_commits`, `fixer_commits_per_pr`, `prs_routed_to_human`,
   `routed_to_human_pct`, `needs_human_comments`, `reverts`,
   `escape_rate_pct` (= reverts/merged), `prs_with_req_id`, `req_id_coverage_pct`,
   `ci_runs_success_pct` (from `gh run list --workflow ci.yml --limit 100 --json conclusion`),
   `measured_at` (UTC ISO timestamp).
5. Keep every `gh` call `|| continue`-safe like `pr-sweeper.yml` does; a single
   PR failing a query must not abort the run.

**Verify**: `bash -n tools/metrics` → exit 0; `tools/metrics | head -30` → a
table whose `prs_opened` ≥ 22 and `threads_total` ≥ 69 (numbers may be higher
now); `tools/metrics --json | jq -e '.threads_silent >= 0'` → `true`.

### Step 2: `.github/workflows/pr-header.yml`

Create a workflow with two jobs:

**Job `req-id`** (`pull_request: [opened, edited, synchronize, reopened]`,
`permissions: contents: read`): fails if neither the PR title nor body matches
`REQ-[A-Z]+-[0-9]+`, printing `::error::PR needs a requirement id from docs/REQUIREMENTS.md`.
Also fails if the id is not present in `docs/REQUIREMENTS.md` on the PR's base branch
(`git show origin/main:docs/REQUIREMENTS.md | grep -q "| $ID "`). Skip (exit 0 with a
notice) for PRs authored by `github-actions[bot]`/`claude[bot]`.

**Job `header`** (same triggers plus `workflow_dispatch` with `pr_number`, plus
`issue_comment: [created]` so it refreshes after bot replies;
`permissions: pull-requests: write, contents: read, actions: read`;
`concurrency: pr-header-${{ PR }}`): builds one markdown comment and upserts it
(find an existing comment containing the marker `<!-- metalab-pr-header -->` with
`gh api repos/$REPO/issues/$PR/comments --paginate --jq '.[] | select(.body | contains("<!-- metalab-pr-header -->")) | .id'`;
`PATCH` it if found, else `POST`). Content:

```markdown
<!-- metalab-pr-header -->
## Trust header · REQ-XXX-NN · risk: <low|human-merge>
**Requirement:** <id and the one-line text from docs/REQUIREMENTS.md>
**Risk tier:** `human-merge` if any changed path matches `.github/**`, `.claude/**`, `contracts/**`, `**/requirements.txt`, `backend/app/modal_app.py`; else `low`. (changed files: `gh pr view $PR --json files --jq '.files[].path'`)
**Named owner(s):** map each changed top-level path to AGENTS.md §4 owners (hard-code the table in the workflow; update when AGENTS.md changes).

### Verified by AI
- ci: <conclusion + run link> · Greptile Review: <conclusion>
- Review threads: <total> (fixed <n>, rejected <n>, silent <n>) — silent threads listed by file:line
- Fixer commits on this PR: <n>/5 cap

### Refused by AI / escalated to a named human
- <each PR comment containing "needs human", quoted first line, author, link> — or "none". Exclude comments containing `<!-- metalab-pr-header -->` (the header itself), here and in the `needs_human_comments` count in `tools/metrics`, so the header never counts or quotes itself.

### Human sign-off (<owner handles>)
- [ ] Checked: …  - [ ] Not checked and why: …  - [ ] Residual risk accepted: …
(copy from the PR template; the owner ticks these before merging on a `human-merge` PR)

### Pipeline metrics (repo-wide, `tools/metrics`, <timestamp>)
<the table from tools/metrics>
```

Use `actions/checkout@v4` (so `tools/metrics` is available) and `GH_TOKEN: ${{ github.token }}`.
Add `timeout-minutes: 10`. Do not post on `pull_request` events from forks
(`github.event.pull_request.head.repo.full_name != github.repository` → skip).

**Verify**: `bash -n` is not applicable; run `actionlint` if available. Then dispatch
on an open PR: `gh workflow run pr-header.yml -f pr_number=<N>` (after the workflow
is on `main` — before that, test the shell parts locally by extracting them into
`tools/metrics --pr <N>`, which you may add as a sub-mode that prints just the
per-PR blocks). Expected: exactly one comment with the marker on PR N; a second
dispatch **updates** it (comment count unchanged).

### Step 2b: `tools/task claim` refuses a task without a requirement id

`tools/task:141-163` (`claim`) never checks the body; `next` (`:132-133`) only
prints "(missing: ask the author to cite one)". In `claim`, after fetching the
issue body, `grep -qE "REQ-[A-Z]+-[0-9]+" <<<"$body" || die "task #$n has no requirement id (docs/REQUIREMENTS.md); add one to the issue first"`.
Use the script's existing `die` helper and quoting style. This makes DX
traceability a gate at the *start* of work, not only at PR time.

**Verify**: `bash -n tools/task` → exit 0; `tools/task claim <an open task without REQ>` → the error message and exit 1 (then add the id to the issue and retry → claimed).

### Step 3: Wire the walkthrough PR

Pick the live walkthrough PR for the Tieto judges (plan 003 names #86 as the
candidate; any merged PR with ≥ 2 Greptile threads and a fixer commit works).
Dispatch `pr-header.yml` on it so the header exists on a *real, merged,
agent-written PR*; link it from `docs/TIETO_CONCEPT_CARD.md` section 7. If one
of its threads is `silent`, reply on that thread now with the true disposition
(`Fixed in <sha>` or `Not changing: <reason>`) and re-dispatch so the header
shows 0 silent.

**Verify**: `gh pr view <N> --json comments --jq '[.comments[].body | select(contains("metalab-pr-header"))] | length'` → `1`; the header shows `silent 0`.

### Step 4 (optional, same PR B): make silence impossible for the fixer

In `claude-fix.yml` prompt, after "Reply `Fixed in <sha>` on every fixed thread",
add the sentence: `For a finding you judge invalid, reply "Not changing: <reason>" and resolve it; never resolve a thread without a reply.`
Humans' agents are covered by AGENTS.md rule 8 (plan 003).

**Verify**: `grep -c "Not changing" .github/workflows/claude-fix.yml` → `1`.

### Step 5: Paste the panel into the concept card and open the PRs

Run `tools/metrics`, paste the table under section 5 of
`docs/TIETO_CONCEPT_CARD.md` with its `measured_at`. Open PR A and PR B per "Git
workflow"; tag `@moterodiaz` for the human merge of PR B; post both links on the board.

## Test plan

- `tools/metrics`: no unit framework for bash here; the gate is `bash -n`, a
  successful run against the live repo, and `--json | jq -e` type checks for
  every key (write them into a tiny `tools/metrics.test.sh` modelled on
  `.claude/hooks/bash-guard.test.sh`, which CI runs if executable? — no: CI only
  runs `bash-guard.test.sh`; run yours by hand and mention it in the PR).
- `pr-header.yml`: one dispatch on a merged PR (Step 3) and one on an open PR;
  confirm upsert (second run edits, doesn't duplicate) and that a PR without a
  REQ id gets a red `req-id` check.

## Done criteria

- [ ] `tools/metrics` exists, executable, `bash -n` clean, prints `threads_total`, `threads_silent`, `ttm_median_min`, `prs_routed_to_human`, `reverts`, `prs_with_req_id`
- [ ] `tools/metrics --json | jq -e 'has("measured_at") and has("disposition_coverage_pct")'` → `true`
- [ ] `.github/workflows/pr-header.yml` exists with jobs `req-id` and `header`, `timeout-minutes` set, fork guard present
- [ ] The walkthrough PR carries exactly one header comment showing the three blocks and `silent 0`
- [ ] A test PR without a REQ id shows a failing `req-id` check (then fix its title and watch it pass)
- [ ] Concept card section 5 contains a `measured_at` timestamp from today
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Any `gh` query returns the GraphQL node-limit error: you requested too much in
  one call; reduce the page size or switch to REST — do not raise `--limit`.
- The header job posts more than one comment on the same PR after two runs
  (upsert broken): fix before enabling triggers beyond `workflow_dispatch`.
- The lead wants the `req-id` check to be a required status check: that is a
  GitHub settings change; hand it to `@moterodiaz` with the exact check name.
- Rate limiting (`API rate limit exceeded`): add `sleep 1` between per-PR calls
  and reduce `--limit`; never retry in a tight loop.

## Maintenance notes

- The owner table inside `pr-header.yml` duplicates `AGENTS.md` §4 until a
  `CODEOWNERS` file exists (plan 007); when it does, read owners from it instead.
- Reviewer: check the workflow never edits code or pushes; it only reads and
  comments. Confirm `permissions` are the minimum listed.
- Re-run `tools/metrics` before the Sunday 10:00 submission and refresh the
  concept card; judges will compare against GitHub.
- Deferred: a per-PR "review time saved" estimate needs a baseline of human
  review minutes the team does not have; report time-to-merge instead and say so.

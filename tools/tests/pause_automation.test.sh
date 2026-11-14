#!/usr/bin/env bash
# Offline tests: claude-fix and pr-sweeper leave PRs labelled integration-paused alone,
# and claude-fix does not race the PR author's own fix.
# Each workflow step's `run:` script is extracted and run against a fake gh (tools/tests/fake_gh.py).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
WF="$HERE/../../.github/workflows"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
ln -s "$HERE/fake_gh.py" "$TMP/bin/gh"
# GNU `date -d` and real sleeps are not needed for these paths; log them instead.
cat > "$TMP/bin/date" <<'SH'
#!/usr/bin/env bash
for a in "$@"; do if [ "$a" = -d ]; then case "$*" in *+%s*) echo 0 ;; *) echo 2026-11-13T00:00:00Z ;; esac; exit 0; fi; done
exec /bin/date "$@"
SH
printf '#!/usr/bin/env bash\necho "sleep $*" >> "$FAKE_GH_LOG"\n' > "$TMP/bin/sleep"
# git rev-parse HEAD reports $FAKE_GIT_HEAD (the runner's local fix commit); anything else is real git.
cat > "$TMP/bin/git" <<'SH'
#!/usr/bin/env bash
if [ "$1 $2" = "rev-parse HEAD" ] && [ -n "${FAKE_GIT_HEAD:-}" ]; then echo "$FAKE_GIT_HEAD"; exit 0; fi
exec /usr/bin/git "$@"
SH
chmod +x "$TMP/bin/date" "$TMP/bin/sleep" "$TMP/bin/git"
export PATH="$TMP/bin:$PATH" FAKE_GH_DB="$TMP/db.json" FAKE_GH_LOG="$TMP/log" REPO=o/r GITHUB_REPOSITORY=o/r \
  GITHUB_OUTPUT="$TMP/out" GITHUB_SERVER_URL=https://github.com GITHUB_RUN_ID=1 GH_TOKEN=x PYTHONDONTWRITEBYTECODE=1

pass=0 failed=0
ok() { pass=$((pass + 1)); }
bad() { failed=$((failed + 1)); echo "FAIL: $*"; }
logged() { grep -qE -- "$1" "$FAKE_GH_LOG"; }
check() { if logged "$2"; then ok; else bad "$1: log lacks /$2/"; fi; }
check_not() { if logged "$2"; then bad "$1: log has /$2/"; else ok; fi; }

# Prints the `run: |` body of the step named $2 in workflow file $1.
step() {
  python3 - "$1" "$2" <<'PY'
import re, sys
lines = open(sys.argv[1]).read().split("\n")
for i, l in enumerate(lines):
    if re.match(r"\s*- name: " + re.escape(sys.argv[2]) + r"\s*$", l):
        for j in range(i + 1, len(lines)):
            m = re.match(r"(\s*)run: \|\s*$", lines[j])
            if m:
                body, ind = [], None
                for k in range(j + 1, len(lines)):
                    if lines[k].strip() == "":
                        body.append(""); continue
                    cur = len(lines[k]) - len(lines[k].lstrip())
                    if ind is None: ind = cur
                    if cur < ind: break
                    body.append(lines[k][ind:])
                print("\n".join(body)); sys.exit(0)
sys.exit("step not found: " + sys.argv[2])
PY
}
run_step() { # file step-name [shell]
  local s; s="$(step "$1" "$2")" || { bad "cannot extract $2"; return 1; }
  : > "$GITHUB_OUTPUT"
  local rc
  bash -c "$s" >> "$TMP/stdout" 2>&1; rc=$?
  if [ "$rc" -ne 0 ] && [ "${EXPECT_FAIL:-0}" != "1" ]; then
    bad "step '$2' exited $rc; output: $(cat "$TMP/stdout")"
  fi
  return "$rc"
}

pr() { # number labels(csv) mergeState automerge(true/false)
  jq -n --argjson n "$1" --arg l "$2" --arg m "$3" --arg a "$4" '{
    number: $n, state: "OPEN", isDraft: false, author: {login: "dev"}, user: {login: "dev"},
    headRefName: ("b" + ($n|tostring)), head: {ref: ("b" + ($n|tostring)), repo: {full_name: "o/r"}, sha: "s"},
    createdAt: "2026-11-13T00:00:00Z", updatedAt: "2026-11-13T00:00:00Z", mergeStateStatus: $m,
    reviews: [], comments: [], statusCheckRollup: [{conclusion: "FAILURE"}],
    autoMergeRequest: (if $a == "true" then {} else null end),
    labels: ($l | split(",") | map(select(. != "")) | map({name: .}))}'
}
reset() { # paused_issue_open(true/false)
  local paused="$1"
  { pr 7 integration-paused DIRTY true; pr 8 "" DIRTY false; } | jq -s --argjson p "$paused" '{
    prs: .,
    issues: (if $p then [{number: 129, state: "OPEN", labels: [{name: "task"}, {name: "integration-paused"}], assignees: [], body: ""}] else [] end),
    api: {
      "repos/o/r/pulls/7": .[0], "repos/o/r/pulls/8": .[1],
      "repos/o/r/issues/7": .[0], "repos/o/r/issues/8": .[1],
      "repos/o/r/pulls/7/commits": [], "repos/o/r/pulls/8/commits": [],
      "repos/o/r/pulls/7/reviews": [], "repos/o/r/pulls/8/reviews": [],
      "repos/o/r/commits/s": {commit: {message: "feat: x"}},
      "repos/o/r/pulls/7/files": [{filename: "backend/app/x.py"}],
      "repos/o/r/issues/1/comments": [], "repos/o/r/issues/7/comments": [], "repos/o/r/issues/8/comments": [],
      "repos/o/r/pulls/7/comments": [], "repos/o/r/pulls/8/comments": [],
      "graphql": {data: {repository: {pullRequest: {reviewThreads: {nodes: [{isResolved: false}]}}}}}
    }}' > "$FAKE_GH_DB"
  : > "$FAKE_GH_LOG"; : > "$TMP/stdout"
}
out_has() { grep -q -- "$1" "$GITHUB_OUTPUT"; }

CF="$WF/claude-fix.yml" SW="$WF/pr-sweeper.yml"

# claude-fix: the hold job fires for the new label too.
grep -qE "github.event.label.name == 'integration-paused'" "$CF" && ok || bad "hold job does not trigger on integration-paused"

reset true
PR=7 LABEL=integration-paused run_step "$CF" "Disable auto-merge"
check "hold disables auto-merge on paused PR" '^pr merge --disable-auto 7'
check "hold comment names the label" 'integration-paused'

reset true
PR_NUMBER=7 run_step "$CF" "Resolve PR and enforce loop cap"
out_has "proceed=false" && ok || bad "paused PR: fix job should not proceed: $(cat "$GITHUB_OUTPUT")"
check "paused PR: fix job disables auto-merge" '^pr merge --disable-auto 7'
check_not "paused PR: fix job reads no commits" 'pulls/7/commits'

reset true
PR_NUMBER=8 run_step "$CF" "Resolve PR and enforce loop cap"
out_has "proceed=true" && ok || bad "normal PR: fix job should proceed: $(cat "$GITHUB_OUTPUT"; cat "$TMP/stdout")"

# Author-push race: skip when the author pushed after Greptile's latest review (#213).
db_set() { jq "$1" "$FAKE_GH_DB" > "$TMP/d" && mv "$TMP/d" "$FAKE_GH_DB"; }
reset true
db_set '.api["repos/o/r/pulls/8/reviews"] = [{user: {login: "greptile-apps[bot]"}, commit_id: "old"}]'
PR_NUMBER=8 GITHUB_EVENT_NAME=pull_request_review run_step "$CF" "Resolve PR and enforce loop cap"
out_has "proceed=false" && ok || bad "author pushed after review: should skip: $(cat "$GITHUB_OUTPUT")"
grep -q "claude-fix skips this run" "$TMP/stdout" && ok || bad "author pushed after review: skip reason not logged"
reset true
db_set '.api["repos/o/r/pulls/8/reviews"] = [{user: {login: "greptile-apps[bot]"}, commit_id: "old"}, {user: {login: "greptile-apps[bot]"}, commit_id: "s"}]'
PR_NUMBER=8 GITHUB_EVENT_NAME=pull_request_review run_step "$CF" "Resolve PR and enforce loop cap"
out_has "proceed=true" && ok || bad "review of the current head: should proceed: $(cat "$GITHUB_OUTPUT")"
reset true
db_set '.api["repos/o/r/pulls/8/reviews"] = [{user: {login: "greptile-apps[bot]"}, commit_id: "old"}] | .api["repos/o/r/commits/s"].commit.message = "fix: address greptile review (#8)"'
PR_NUMBER=8 GITHUB_EVENT_NAME=pull_request_review run_step "$CF" "Resolve PR and enforce loop cap"
out_has "proceed=true" && ok || bad "head is the bot's own fix: should proceed: $(cat "$GITHUB_OUTPUT")"
reset true
db_set '.api["repos/o/r/pulls/8/reviews"] = [{user: {login: "greptile-apps[bot]"}, commit_id: "old"}]'
PR_NUMBER=8 GITHUB_EVENT_NAME=workflow_dispatch run_step "$CF" "Resolve PR and enforce loop cap"
out_has "proceed=true" && ok || bad "dispatch (sweeper retry) always runs: $(cat "$GITHUB_OUTPUT")"
check_not "dispatch reads no reviews" 'pulls/8/reviews'

# Head moved during the run: no push.
reset true
PR_NUMBER=8 BEFORE_SHA=s run_step "$CF" "Recheck head"
out_has "moved=false" && ok || bad "recheck head: unchanged head should output moved=false"
reset true
PR_NUMBER=8 BEFORE_SHA=earlier run_step "$CF" "Recheck head"
out_has "moved=true" && ok || bad "recheck head: moved head should output moved=true"
grep -qE "steps\.head\.outputs\.moved != 'true'" "$CF" && ok || bad "push steps must gate on steps.head.outputs.moved"

# A discarded fix commit reopens the threads Claude marked "Fixed in <sha>", and only those.
reset true
db_set '.api.graphql.data.repository.pullRequest.reviewThreads.nodes = [
  {id: "T1", isResolved: true, comments: {nodes: [{body: "Fixed in abc1234"}]}},
  {id: "T2", isResolved: true, comments: {nodes: [{body: "Not changing: out of scope"}]}},
  {id: "T3", isResolved: false, comments: {nodes: [{body: "Fixed in abc1234"}]}}]'
FAKE_GIT_HEAD=abc1234567 PR_NUMBER=8 BEFORE_SHA=s run_step "$CF" "Reopen threads whose fix was not pushed"
check "discarded fix: reopens its thread" 'unresolveReviewThread.* t=T1'
check "discarded fix: says it was not pushed" 't=T1 -f b=Not pushed'
check_not "discarded fix: leaves a rejected thread alone" 't=T2'
check_not "discarded fix: leaves an open thread alone" 't=T3'
reset true
FAKE_GIT_HEAD=s PR_NUMBER=8 BEFORE_SHA=s run_step "$CF" "Reopen threads whose fix was not pushed"
check_not "no local commit: reopens nothing" 'unresolveReviewThread'
grep -qE "steps\.push\.outcome == 'failure'" "$CF" && ok || bad "reopen step must also run when the push fails"
# The skip rule must not cover the fixer's own replies, or a reopened thread is never retried.
grep -q "anyone other than greptile-apps, claude and" "$CF" && ok || bad "prompt must exempt the fixer's own replies from the skip rule"
reset true
db_resolved() { jq '.api.graphql.data.repository.pullRequest.reviewThreads.nodes = []' "$FAKE_GH_DB" > "$TMP/d" && mv "$TMP/d" "$FAKE_GH_DB"; }
db_resolved
PR_NUMBER=7 BEFORE_SHA=s run_step "$CF" "Enable auto-merge when review threads are resolved"
check_not "paused PR: auto-merge never enabled" '^pr merge --auto'
check "paused PR: auto-merge step disables auto-merge" '^pr merge --disable-auto 7'
reset true; db_resolved
jq '.api["repos/o/r/pulls/8/files"] = [{filename: "backend/app/x.py"}]' "$FAKE_GH_DB" > "$TMP/d" && mv "$TMP/d" "$FAKE_GH_DB"
PR_NUMBER=8 BEFORE_SHA=s run_step "$CF" "Enable auto-merge when review threads are resolved"
check "normal PR: auto-merge still enabled" '^pr merge --auto --squash 8'

# Recheck integration-paused step: re-reads label before push (Thread 2).
reset true
PR_NUMBER=7 run_step "$CF" "Recheck integration-paused"
out_has "paused=true" && ok || bad "recheck: label present should output paused=true"

reset true
PR_NUMBER=8 run_step "$CF" "Recheck integration-paused"
out_has "paused=false" && ok || bad "recheck: label absent should output paused=false"

reset true
FAKE_GH_FAIL="pr view 7" PR_NUMBER=7 run_step "$CF" "Recheck integration-paused"
out_has "paused=true" && ok || bad "recheck: failed label read should output paused=true (fail-closed)"

# pr-sweeper: no nudges, pings or retries for a paused PR; the control PR still gets them.
reset true
run_step "$SW" "Sweep open PRs"
check "sweep nudges review on normal PR" '^pr comment 8 .*@greptileai review'
check_not "sweep does not nudge paused PR" '^pr comment 7'
check_not "sweep posts nothing about paused PR" 'PR #7'

reset true
run_step "$SW" "Retry stuck claude-fix"
check "retry looks at normal PR" 'n=8'
check_not "retry skips paused PR" 'n=7|pr_number=7'

# Queue check: no "task queue low" (which sends agents to fill) while the pause is active.
reset true
run_step "$SW" "Clean in-progress labels and check task queue"
check_not "paused: no task-queue-low post" 'task queue low'
reset false
run_step "$SW" "Clean in-progress labels and check task queue"
check "released: task-queue-low post resumes" 'task queue low'

# Heartbeat ignores paused PRs when deciding to keep re-running.
reset true
jq '(.prs[1].mergeStateStatus) = "CLEAN"' "$FAKE_GH_DB" > "$TMP/d" && mv "$TMP/d" "$FAKE_GH_DB"
chain=0 run_step "$SW" "Heartbeat"
check_not "heartbeat ignores a dirty paused PR" '^sleep|workflow run'
reset true
chain=0 run_step "$SW" "Heartbeat"
check "heartbeat still chains for a dirty normal PR" '^workflow run pr-sweeper.yml'

# Early pause check: new step runs before secrets and outputs paused correctly.
reset true
PR_NUMBER=7 run_step "$CF" "Check integration-paused"
out_has "paused=true" && ok || bad "early pause: labelled PR should output paused=true: $(cat "$GITHUB_OUTPUT")"

reset true
PR_NUMBER=8 run_step "$CF" "Check integration-paused"
out_has "paused=false" && ok || bad "early pause: unlabelled PR should output paused=false: $(cat "$GITHUB_OUTPUT")"

# Structural: Require Claude token and Alert on failure must carry the paused guard.
grep -qE "steps\.pause\.outputs\.paused != 'true'" "$CF" && ok || bad "workflow must gate on steps.pause.outputs.paused"

echo "pause_automation.test.sh: $pass passed, $failed failed"
[ "$failed" -eq 0 ]

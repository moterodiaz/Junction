#!/usr/bin/env bash
# Offline tests for the priority-lane and integration-pause rules in tools/task.
# A fake gh (tools/tests/fake_gh.py) serves fixture issues; nothing touches GitHub.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
TASK="$HERE/../task"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"
ln -s "$HERE/fake_gh.py" "$TMP/bin/gh"
printf '#!/usr/bin/env bash\necho "board $*" >> "$FAKE_GH_LOG"\n' > "$TMP/board"
chmod +x "$TMP/board"
export PATH="$TMP/bin:$PATH" FAKE_GH_DB="$TMP/db.json" FAKE_GH_LOG="$TMP/log" BOARD_REPO=o/r \
  TASK_BOARD="$TMP/board" TASK_AGENTS_FILE=/dev/null PYTHONDONTWRITEBYTECODE=1

pass=0 failed=0
ok() { pass=$((pass + 1)); }
bad() { failed=$((failed + 1)); echo "FAIL: $*"; }

lane() { printf '## Lane\nOwner: @%s\nOrder: %s\n' "$1" "$2"; }
issue() { # number login(or "") labels(csv) created body
  jq -n --argjson n "$1" --arg a "$2" --arg l "$3" --arg c "$4" --arg b "$5" '{
    number: $n, title: ("task " + ($n|tostring)), state: "OPEN", createdAt: $c, body: $b,
    assignees: (if $a == "" then [] else [{login: $a}] end),
    labels: ($l | split(",") | map(select(. != "")) | map({name: .}))}'
}

reset_db() {
  {
    issue 182 Ahm3d-KA task,priority-lane 2026-11-14T10:00:00Z "$(printf '## PRD section\n§12.9\n## Requirement\nREQ-PROC-01\n## Depends on\nnone\n'; lane Ahm3d-KA 1)"
    issue 190 "" task,priority-lane,needs-owner-ok 2026-11-14T11:00:00Z "$(printf '## Requirement\nREQ-PROC-02\n## Depends on\n#182\n'; lane Ahm3d-KA 2)"
    issue 191 maksymmatviievskyi task,priority-lane,needs-owner-ok 2026-11-14T11:01:00Z "$(printf '## Requirement\nREQ-IOS-03\n## Depends on\nnone\n'; lane maksymmatviievskyi 1)"
    issue 192 Marcus228 task,priority-lane,needs-owner-ok 2026-11-14T11:02:00Z "$(printf '## Requirement\nREQ-VOICE-02\n## Depends on\nnone\n'; lane Marcus228 1)"
    issue 81 "" task,integration-paused 2026-11-13T09:00:00Z "$(printf '## Requirement\nREQ-INT-01\n## Depends on\nnone\n## Area\ncontracts\n')"
    issue 129 "" task,blocked,integration-paused 2026-11-13T09:01:00Z "$(printf '## Requirement\nREQ-SRC-01\n## Depends on\nnone\n')"
    issue 150 "" task,integration-paused 2026-11-13T09:02:00Z "$(printf '## Requirement\nREQ-INTENT-01\n## Depends on\n#129\n')"
    issue 130 Ahm3d-KA task,in-progress,integration-paused 2026-11-13T09:03:00Z "$(printf '## Requirement\nREQ-PROC-01\n')"
    issue 200 "" task 2026-11-13T12:00:00Z "$(printf '## Requirement\nREQ-PROC-01\n## Depends on\nnone\n')"
  } | jq -s '{issues: .}' > "$FAKE_GH_DB"
  : > "$FAKE_GH_LOG"
}
db() { jq "$1" "$FAKE_GH_DB" > "$TMP/db.new" && mv "$TMP/db.new" "$FAKE_GH_DB"; }
close() { db "(.issues[] | select(.number == $1) | .state) = \"CLOSED\""; }
unpause_all() { db '(.issues[].labels) |= map(select(.name != "integration-paused"))'; }

as() { local who="$1"; shift; FAKE_GH_LOGIN="$who" "$TASK" "$@" 2>&1; }
expect() { # name expected_status pattern who args...
  local name="$1" want="$2" pat="$3" who="$4" out rc; shift 4
  out="$(as "$who" "$@")"; rc=$?
  if [ "$want" = ok ] && [ "$rc" -ne 0 ]; then bad "$name: exit $rc: $out"; return; fi
  if [ "$want" = fail ] && [ "$rc" -eq 0 ]; then bad "$name: expected failure: $out"; return; fi
  printf '%s\n' "$out" | grep -qE -- "$pat" && ok || bad "$name: output lacks /$pat/: $out"
}
refute() { # name pattern who args... (output must not match)
  local name="$1" pat="$2" who="$3" out; shift 3
  out="$(as "$who" "$@")"
  printf '%s\n' "$out" | grep -qE -- "$pat" && bad "$name: output matched /$pat/: $out" || ok
}
assignees_of() { jq -r ".issues[] | select(.number == $1) | [.assignees[].login] | join(\",\")" "$FAKE_GH_DB"; }

reset_db
# Ahmed: lane step 1 is #182, already assigned to him.
expect "ahmed next returns assigned #182" ok '^#182 .*' Ahm3d-KA next
expect "ahmed next says assigned" ok 'Assigned to you' Ahm3d-KA next
refute "ahmed next never offers backlog" '#81|#200|#150' Ahm3d-KA next
expect "ahmed claim paused #81 rejected" fail 'paused integration backlog' Ahm3d-KA claim 81
expect "ahmed claim maksym lane rejected" fail "maksymmatviievskyi's priority-lane task" Ahm3d-KA claim 191
expect "ahmed claim step 2 out of order rejected" fail '#182 comes before #190' Ahm3d-KA claim 190
expect "ahmed claim unrelated #200 rejected" fail 'open priority lane' Ahm3d-KA claim 200
expect "ahmed claim own assigned #182 is a no-op" ok 'already yours' Ahm3d-KA claim 182
expect "ahmed fill does not refill" ok 'Priority lane open \(#182\)' Ahm3d-KA fill
refute "ahmed fill never says queue low" 'Queue low|gh issue create' Ahm3d-KA fill

# Maksym and Marcus get their own pre-assigned tasks with the confirmation reminder.
expect "maksym next returns #191" ok '^#191 ' maksymmatviievskyi next
expect "maksym next asks for owner confirmation" ok 'ask your human to confirm' maksymmatviievskyi next
expect "maksym claim own task is a no-op" ok 'already yours' maksymmatviievskyi claim 191
expect "marcus next returns #192" ok '^#192 ' Marcus228 next
expect "marcus claim ahmed lane rejected" fail "ahm3d-ka's priority-lane task" Marcus228 claim 190
expect "marcus claim paused #150 rejected" fail 'paused integration backlog' Marcus228 claim 150

# Ahmed's lane advances once #182 closes.
close 182
expect "ahmed next advances to #190" ok '^#190 ' Ahm3d-KA next
expect "ahmed next offers claim of #190" ok 'Next: tools/task claim 190' Ahm3d-KA next
expect "ahmed claims #190" ok 'Claimed #190' Ahm3d-KA claim 190
[ "$(assignees_of 190)" = Ahm3d-KA ] && ok || bad "#190 not assigned to Ahmed: $(assignees_of 190)"
grep -q 'board post \[Ahm3d-KA.s agent\] claimed #190' "$FAKE_GH_LOG" && ok || bad "claim not announced on board"
expect "ahmed next shows #190 assigned" ok 'Assigned to you' Ahm3d-KA next

# A finished lane waits while the pause is active.
close 190
expect "ahmed finished lane waits" ok 'Wait: do not claim' Ahm3d-KA next
refute "ahmed finished lane gets no fallback" '#81|#200|#150|claim [0-9]' Ahm3d-KA next
expect "ahmed finished lane: claim #200 rejected" fail 'paused and your lane is finished' Ahm3d-KA claim 200
expect "ahmed finished lane: claim #81 rejected" fail 'paused integration backlog' Ahm3d-KA claim 81
expect "ahmed finished lane: fill waits" ok 'paused by @moterodiaz' Ahm3d-KA fill

# A blocked lane waits too; it does not fall through to step 2 or the backlog.
reset_db
db '(.issues[] | select(.number == 182) | .assignees) = [] | (.issues[] | select(.number == 182) | .labels) += [{name: "blocked"}]'
expect "blocked lane waits" ok 'Waiting: #182 is labelled blocked' Ahm3d-KA next
refute "blocked lane offers nothing else" 'claim [0-9]|#190 |#81|#200' Ahm3d-KA next
expect "blocked lane step cannot be claimed" fail 'labelled blocked' Ahm3d-KA claim 182
expect "blocked lane: next step still out of order" fail '#182 comes before #190' Ahm3d-KA claim 190
# Step 2 waiting on an open dependency is reported, not skipped.
reset_db
db '(.issues[] | select(.number == 182) | .assignees) = [{login: "someone"}]'
expect "lane step held by someone else waits" ok 'Waiting: #182 is assigned to @someone' Ahm3d-KA next
reset_db
db '(.issues[] | select(.number == 182) | .labels) |= map(select(.name != "priority-lane"))'
expect "lane step with open dependency waits" ok 'Waiting: #190 has open' Ahm3d-KA next
expect "claim of step with open dependency rejected" fail 'open \(or unreadable\) dependencies' Ahm3d-KA claim 190

# (a) An assigned lane step that is blocked is refused by both next and claim.
reset_db
db '(.issues[] | select(.number == 182) | .labels) += [{name: "blocked"}]'
expect "assigned blocked lane: next shows waiting" ok 'Waiting: #182 is labelled blocked' Ahm3d-KA next
expect "assigned blocked lane: claim refused" fail 'labelled blocked' Ahm3d-KA claim 182

# (b) An assigned later lane step is refused while an earlier step remains open.
reset_db
db '(.issues[] | select(.number == 190) | .assignees) = [{login: "Ahm3d-KA"}]'
expect "assigned step-2 refused by claim while step-1 open" fail '#182 comes before #190' Ahm3d-KA claim 190
refute "assigned step-2: next does not continue #190" 'Continue.*190|190.*Continue' Ahm3d-KA next

# (c) An assigned, unblocked, in-order lane step still returns 'already yours'.
reset_db
expect "assigned in-order unblocked: claim returns already-yours" ok 'already yours' Ahm3d-KA claim 182
expect "assigned in-order unblocked: next says assigned" ok 'Assigned to you' Ahm3d-KA next

# Mateo keeps the backlog; dependency gates still hold.
reset_db
expect "mateo next gets oldest ready paused task" ok '^#81 ' moterodiaz next
refute "mateo next skips blocked/dependent/lane tasks" '^#(129|150|190|191|192) ' moterodiaz next
expect "mateo claim blocked #129 rejected" fail 'labelled blocked' moterodiaz claim 129
expect "mateo claim #150 with open dependency rejected" fail 'open \(or unreadable\) dependencies' moterodiaz claim 150
expect "mateo claim another owner's lane rejected" fail "marcus228's priority-lane task" moterodiaz claim 192
expect "mateo claim ahmed's assigned paused #130 rejected" fail 'already has an assignee' moterodiaz claim 130
expect "mateo claims paused #81" ok 'Claimed #81' moterodiaz claim 81
[ "$(assignees_of 81)" = moterodiaz ] && ok || bad "#81 not assigned to Mateo"
expect "mateo fill counts the queue" ok 'Queue (ok|low)' moterodiaz fill
expect "lead is case-insensitive" ok '^#200 |^#81 ' MoteroDiaz next

# A gh error reading the pause counts as paused (fail closed).
reset_db; close 182; close 190
FAKE_GH_FAIL='--label integration-paused' expect "pause read error waits" ok 'Wait: do not claim' Ahm3d-KA next
# A lane read error stops instead of guessing.
FAKE_GH_FAIL='--label priority-lane' expect "lane read error fails" fail 'could not list priority-lane' Ahm3d-KA next

# Only the lead's release (no open paused issue) lets a finished lane take general work.
unpause_all
expect "after release ahmed gets general work" ok '^#(81|200) ' Ahm3d-KA next
expect "after release ahmed may claim #200" ok 'Claimed #200' Ahm3d-KA claim 200
# Lanes still come first after a release.
expect "after release marcus still gets his lane" ok '^#192 ' Marcus228 next

# Lane task with integration-paused: non-lead owner must be refused.
# #191 is maksymmatviievskyi's lane step 1, already assigned to them; add integration-paused.
reset_db
db '(.issues[] | select(.number == 191) | .labels) += [{name: "integration-paused"}]'
expect "paused lane claim rejected for non-lead owner" fail 'paused' maksymmatviievskyi claim 191
expect "paused lane next shows Waiting/paused (not Continue)" ok 'Waiting.*integration-paused' maksymmatviievskyi next
refute "paused lane next does not say Continue" 'Continue' maksymmatviievskyi next
# Same task without integration-paused: owner may still continue.
reset_db
expect "unpaused lane: claim returns already-yours" ok 'already yours' maksymmatviievskyi claim 191
expect "unpaused lane: next says Assigned to you" ok 'Assigned to you' maksymmatviievskyi next
# Unassigned lane step with integration-paused: next offers Waiting, not claim.
reset_db
db '(.issues[] | select(.number == 182) | .assignees) = [] | (.issues[] | select(.number == 182) | .labels) += [{name: "integration-paused"}]'
expect "unassigned paused lane: next shows Waiting" ok 'Waiting.*integration-paused' Ahm3d-KA next
refute "unassigned paused lane: next does not offer claim" 'Next: tools/task claim 182' Ahm3d-KA next
# Lead keeps existing behavior: not blocked by pause-label check (is_exempt guard).
reset_db
db '(.issues[] | select(.number == 191) | .labels) += [{name: "integration-paused"}]'
expect "lead claim other owner paused lane: owner error not pause" fail "maksymmatviievskyi's priority-lane" moterodiaz claim 191

echo "task.test.sh: $pass passed, $failed failed"
[ "$failed" -eq 0 ]

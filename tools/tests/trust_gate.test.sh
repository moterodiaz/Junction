#!/usr/bin/env bash
# Offline tests for `tools/metrics --gate` (the required `trust` status, REQ-PROC-02): a fake `gh` on PATH
# serves PRs, reviews and escape issues from a JSON file. Areas come from the repo's .github/CODEOWNERS.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -r "$tmp"' EXIT
export FAKE_DB="$tmp/db.json" METRICS_REPO=o/r PATH="$tmp:$PATH"

cat > "$tmp/gh" <<'SH'
#!/usr/bin/env bash
exec python3 - "$@" <<'PY'
import json, os, re, sys
args, db = sys.argv[1:], json.load(open(os.environ["FAKE_DB"]))
if db.get("fail"):
    sys.exit("fake gh: HTTP 502")
if args[:2] == ["issue", "list"]:
    print(json.dumps([{"number": n, "state": e["state"], "body": e["body"]} for n, e in db["escapes"].items()]))
    sys.exit()
path = next(a for a in args if a.startswith("repos/"))
m = re.fullmatch(r"repos/o/r/pulls/(\d+)(/files|/reviews)?(\?per_page=100)?", path)
pr = db["prs"][m.group(1)]
if m.group(2) == "/files":
    print("\n".join(pr["files"]))
elif m.group(2) == "/reviews":
    print("\n".join("\t".join(r) for r in pr.get("reviews", [])))
else:
    print(json.dumps({"head": {"sha": pr["head"]}}))
PY
SH
chmod +x "$tmp/gh"

fails=0
expect() {  # expect <want exit> <want substring> <PR>
  local out code=0
  out="$("$root/tools/metrics" --gate "$3" 2>&1)" || code=$?
  if [ "$code" = "$1" ] && [[ "$out" == *"$2"* ]]; then
    echo "ok   #$3 exit $code: $out"
  else
    echo "FAIL #$3: want exit $1 with '$2', got exit $code: $out"; fails=$((fails + 1))
  fi
}
db() { printf '%s' "$1" > "$FAKE_DB"; }

prs='"40": {"head": "a", "files": ["backend/app/pipeline.py"]},
     "50": {"head": "h2", "files": ["backend/app/main.py", "backend/tests/test_ws.py"], "reviews": REVIEWS},
     "51": {"head": "c", "files": ["backend/ai/page_reader.py"]}'
state() {  # state <escape state> <reviews of #50>
  db "{\"prs\": {${prs/REVIEWS/$2}}, \"escapes\": {\"140\": {\"state\": \"$1\", \"body\": \"Introduced-by: #40\"}}}"
}

echo "earned: no open escape"
state CLOSED '[]';  expect 0 "trust earned in @Ahm3d-KA" 50

echo "withdrawn: open escape #140 was introduced by #40 in @Ahm3d-KA's area"
state OPEN '[]';    expect 3 "held: @Ahm3d-KA trust withdrawn (#140)" 50
expect 0 "trust earned in @Marcus228" 51   # another area still auto-merges
state OPEN '[["Ahm3d-KA", "APPROVED", "h1"]]'
expect 3 "held:" 50                        # approval of an older commit does not cover new code
state OPEN '[["Marcus228", "APPROVED", "h2"]]'
expect 3 "held:" 50                        # only the area owner or the lead
state OPEN '[["Ahm3d-KA", "APPROVED", "h2"]]'
expect 0 "owner-approved head commit" 50
state OPEN '[["moterodiaz", "APPROVED", "h2"]]'
expect 0 "owner-approved head commit" 50   # the lead, for an owner who authored the PR
state OPEN '[["moterodiaz", "APPROVED", "h2"], ["moterodiaz", "CHANGES_REQUESTED", "h2"]]'
expect 3 "held:" 50                        # a later change request withdraws the approval

echo "re-earned: escape #140 closed with its fix"
state CLOSED '[]';  expect 0 "trust earned in @Ahm3d-KA" 50

echo "gh failure fails closed (exit other than 0 or 3)"
db '{"fail": true}'
code=0; "$root/tools/metrics" --gate 50 >/dev/null 2>&1 || code=$?
if [ "$code" != 0 ] && [ "$code" != 3 ]; then echo "ok   exit $code"; else echo "FAIL gh failure gave exit $code"; fails=$((fails + 1)); fi

[ "$fails" = 0 ] && echo "trust gate tests: OK" || { echo "trust gate tests: $fails failed"; exit 1; }

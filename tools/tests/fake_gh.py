#!/usr/bin/env python3
"""Offline stand-in for the parts of `gh` that tools/task and the PR workflows use.

State lives in $FAKE_GH_DB (JSON: issues, prs, api); every call is appended to $FAKE_GH_LOG.
--jq filters run through the real `jq -r`, as gh does. A call whose argv contains
$FAKE_GH_FAIL fails, to exercise error paths.
"""
import json, os, subprocess, sys

args = sys.argv[1:]
db_path = os.environ["FAKE_GH_DB"]
with open(os.environ.get("FAKE_GH_LOG", "/dev/null"), "a") as log:
    log.write(" ".join(args) + "\n")
fail = os.environ.get("FAKE_GH_FAIL")
if fail and fail in " ".join(args):
    sys.exit(1)
db = json.load(open(db_path))
login = os.environ.get("FAKE_GH_LOGIN", "nobody")


def opt(name, many=False):
    vals, i = [], 0
    while i < len(args):
        if args[i] == name and i + 1 < len(args):
            vals.append(args[i + 1]); i += 2
        else:
            i += 1
    return vals if many else (vals[-1] if vals else None)


def emit(value):
    q = opt("--jq")
    data = json.dumps(value)
    if q is None:
        print(data); return
    r = subprocess.run(["jq", "-r", q], input=data, text=True, capture_output=True)
    sys.stdout.write(r.stdout); sys.stderr.write(r.stderr)
    sys.exit(r.returncode)


def save():
    json.dump(db, open(db_path, "w"), indent=1)


def find(kind, n):
    for it in db.get(kind, []):
        if it["number"] == int(n):
            return it
    sys.stderr.write("not found\n"); sys.exit(1)


def names(it):
    return [l["name"] for l in it.get("labels", [])]


cmd = args[:2]
if args[:2] == ["auth", "status"]:
    sys.exit(0)
if args[:1] == ["api"]:
    rest, path = args[1:], None
    while rest:
        a = rest.pop(0)
        if a in ("-f", "-F", "--jq", "-X", "-H", "--method"):
            rest = rest[1:]
        elif not a.startswith("-"):
            path = a; break
    if path == "user":
        emit({"login": login})
    elif path in db.get("api", {}):
        emit(db["api"][path])
    elif path.split("?")[0] in db.get("api", {}):
        emit(db["api"][path.split("?")[0]])
    else:
        sys.stderr.write("no fake api for " + path + "\n"); sys.exit(1)
elif cmd == ["issue", "list"] or cmd == ["pr", "list"]:
    kind = "issues" if args[0] == "issue" else "prs"
    state = (opt("--state") or "open").upper()
    want = opt("--label", many=True)
    out = [it for it in db.get(kind, [])
           if (state == "ALL" or it.get("state", "OPEN") == state) and all(w in names(it) for w in want)]
    emit(out[: int(opt("--limit") or 30)])
elif cmd == ["issue", "view"] or cmd == ["pr", "view"]:
    emit(find("issues" if args[0] == "issue" else "prs", args[2]))
elif cmd == ["issue", "edit"]:
    it = find("issues", args[2])
    me = lambda v: login if v == "@me" else v
    for v in opt("--add-assignee", True):
        it.setdefault("assignees", []).append({"login": me(v)})
    for v in opt("--remove-assignee", True):
        it["assignees"] = [a for a in it.get("assignees", []) if a["login"] != me(v)]
    for v in opt("--add-label", True):
        if v not in names(it): it.setdefault("labels", []).append({"name": v})
    for v in opt("--remove-label", True):
        it["labels"] = [l for l in it.get("labels", []) if l["name"] != v]
    save()
elif cmd == ["pr", "merge"]:
    if "--disable-auto" in args:
        pr = find("prs", [a for a in args[2:] if a.isdigit()][0])
        pr["autoMergeRequest"] = None; save()
elif cmd in (["pr", "comment"], ["workflow", "run"], ["run", "list"], ["run", "cancel"]):
    if cmd == ["run", "list"]:
        emit(db.get("runs", []))
else:
    sys.stderr.write("fake gh: unsupported: " + " ".join(args) + "\n"); sys.exit(2)

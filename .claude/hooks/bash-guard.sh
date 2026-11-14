#!/usr/bin/env bash
# PreToolUse (Bash): block dangerous commands before they run.
# Fail open: any parsing error exits 0 so sessions are never broken by this hook.

command -v jq >/dev/null 2>&1 || exit 0
cmd="$(jq -r '.tool_input.command // empty' 2>/dev/null)" || exit 0
[ -n "$cmd" ] || exit 0

# (a) Secret / env file references — block .env* but allow .env.example/.env.sample/.env.template
for word in $cmd; do
  case "$word" in
    *.env.example*|*.env.sample*|*.env.template*) ;;
    *.env*|*id_rsa*|*.pem*|*.p12*|*credentials.json*)
      echo "Blocked: command references a secret file: $word" >&2; exit 2 ;;
  esac
done

# (b) Dangerous git push flags and protected branch names / refspecs
case "$cmd" in
  *git\ push*)
    for word in $cmd; do
      case "$word" in
        -f|--force|--force-with-lease|--force-with-lease=*)
          echo "Blocked: dangerous git push flag: $word" >&2; exit 2 ;;
        --delete|-d|--mirror|--prune)
          echo "Blocked: dangerous git push option: $word" >&2; exit 2 ;;
        main|master)
          echo "Blocked: git push to protected branch: $word" >&2; exit 2 ;;
        +*)
          echo "Blocked: git push force refspec: $word" >&2; exit 2 ;;
        *:main|*:master|*refs/heads/main|*refs/heads/master)
          echo "Blocked: git push to protected branch via refspec: $word" >&2; exit 2 ;;
      esac
    done
  ;;
esac

# (c) gh api graphql with PR review approve mutations
case "$cmd" in
  *gh\ api*graphql*)
    case "$cmd" in
      *addPullRequestReview*|*submitPullRequestReview*|*APPROVE*)
        echo "Blocked: gh api graphql PR review/approve mutation is forbidden" >&2; exit 2 ;;
    esac
  ;;
esac

# (d) gh pr merge --admin
case "$cmd" in
  *gh\ pr\ merge*--admin*)
    echo "Blocked: gh pr merge --admin is forbidden" >&2; exit 2 ;;
esac

# (e) gh pr review --approve / -a
case "$cmd" in
  *gh\ pr\ review*)
    for word in $cmd; do
      case "$word" in
        --approve|-a)
          echo "Blocked: gh pr review --approve/-a is forbidden" >&2; exit 2 ;;
      esac
    done
  ;;
esac

exit 0

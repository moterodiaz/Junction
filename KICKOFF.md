# Kickoff
MetaLab session bootstrap: get every teammate's agent running in its own worktree and claiming tasks.

## Before the team arrives (lead)

- Invites accepted (empty list = none pending): `gh api repos/moterodiaz/Junction/invitations`
- Secrets exist: `CLAUDE_CODE_OAUTH_TOKEN` and `BOT_PUSH_TOKEN` (PAT, 90-day expiry; renew: `gh secret set BOT_PUSH_TOKEN`)
- main-protect ruleset requires `ci` and `Greptile Review`

## Each person, once

1. Accept your repository invite.
2. `gh auth login`
3. Clone the repo.
4. Merge the user settings block below into `~/.claude/settings.json`.
5. Run `tools/onboard` from your clone until READY (a WARN about being on main is fine here), then `tools/task next`, `tools/task claim N`, and `tools/wt N-slug`.

## Lead: split the work

Edit the owner table in `AGENTS.md` section 4 by hand: set the GitHub login for the ios, backend and contracts rows, then open the PR.

Suggested default (not a rule): lead = contracts + integration; one person backend core (config, latency, stt, errors); one person backend AI (reading, reasoning, image, sources); one person ios.

## The work cycle
See AGENTS.md START HERE: `tools/task next`, `tools/task claim N`, `tools/wt N-slug`, PR with `Closes #N`, then `tools/task next` again.

## If something looks stuck

1. Read PR comments for `needs human`.
2. Read the board (`tools/board unread`).
3. Check the Actions tab.
4. `gh workflow run claude-fix.yml -f pr_number=N` retries the bot.
5. A conflict goes on the board per AGENTS.md section 6.

## What is not hands-off

PRs touching `.github/workflows/**` or `.claude/settings.json` need one human merge. Expired secrets must be rotated by a human. The Bash guard hook guards against accidents and obvious secret-file paths, NOT a sandbox.

## User settings block
Paste into `~/.claude/settings.json` (merge arrays into existing arrays; create the file if absent).

```json
{
  "permissions": {
    "allow": [
      "Bash(gh pr create *)","Bash(gh pr view *)","Bash(gh pr list *)","Bash(gh pr comment *)","Bash(gh pr checks *)",
      "Bash(gh pr merge *)","Bash(gh issue list *)","Bash(gh issue view *)","Bash(gh run list *)","Bash(gh run view *)",
      "Bash(gh run watch *)","Bash(gh workflow run *)","Bash(git switch *)","Bash(git add *)","Bash(git commit *)",
      "Bash(git fetch *)","Bash(git pull --no-rebase*)","Bash(git push -u origin *)","Bash(git push)",
      "Bash(tools/board *)","Bash(tools/task *)","Bash(tools/wt *)","Bash(tools/onboard*)","Bash(tools/kickoff *)"
    ],
    "deny": [
      "Bash(gh pr merge *--admin*)","Bash(gh pr review --approve*)","Bash(git push*--force*)","Bash(git push*--delete*)"
    ]
  },
  "autoMode": {
    "environment": [
      "$defaults",
      "Source control: github.com/moterodiaz/Junction (this repo, its PR branches and its main-protect ruleset)"
    ],
    "allow": [
      "$defaults",
      "Squash-merging a pull request in github.com/moterodiaz/Junction with gh pr merge is allowed once the required checks pass and review threads are resolved; the main-protect ruleset enforces this and has no bypass actors",
      "Committing, pushing branches and opening pull requests in github.com/moterodiaz/Junction is allowed, because changes reach main only through a PR gated by the main-protect ruleset",
      "Posting comments, replying to and resolving review threads, claiming tasks with tools/task and starting the claude-fix workflow with gh workflow run in github.com/moterodiaz/Junction is allowed"
    ],
    "hard_deny": [
      "$defaults",
      "Never use gh pr merge --admin, push directly to main, force-push, or edit or disable the main-protect ruleset"
    ]
  }
}
```

autoMode only works in the USER settings file (Claude Code ignores it in project settings); verify with `claude auto-mode config`.

# MetaLab: Tieto track video, 2:00 (draft)

Script and shot list for Tieto's "Earned Trust in AI Code" track (#207, LANE-A5). Recording and submitting stay with the lead (#145). Tags point to `docs/pitch/SOURCES.md`. Everything on screen is a real GitHub page, or a terminal running a command from this repo: no glasses are needed.

| Time | On screen | Voice-over | Source |
|---|---|---|---|
| 0:00–0:12 | PR #174 merging through auto-merge | "An agent opened a PR in my area. Seven minutes later it was merged. Could I put my name on it?" | E19 |
| 0:12–0:35 | PR #174's trust header, rendered with `tools/metrics --pr 174`: requirement REQ-WS-01, checks, two findings, two refusals, the sign-off box | "Every change names its requirement and its owner. The AI says what it fixed, and what it refused to decide and why." | E19 |
| 0:35–0:55 | The reply "Not changing in this PR: … Marcus's area", then issue #175 and PR #178 | "Here it refused to touch a teammate's code. It filed an issue instead, and the teammate fixed it." | E19 |
| 0:55–1:20 | The live drill: escape #193 filed; #191 turns BLOCKED with "held: trust withdrawn"; #193 closes; #191 is mergeable again | "When a bug slips through, that area loses its trust. GitHub blocks merges there until the owner signs. Live, that took 15 seconds." | E19 |
| 1:20–1:40 | Terminal: the `tools/metrics` table | "54 PRs. 131 AI findings, 93 fixed with a named commit. 13% let a defect through, and we show that number." | E18 |
| 1:40–1:52 | The limits list from `docs/pitch/tieto-submission.md` | "What we can't see: what the reviewer missed. No baseline, one weekend." | E19 |
| 1:52–2:00 | Closing card | "AI reviews with evidence. A named human owns it. Trust is earned per area, and taken back." | — |

## Rules for the edit

- **Re-run `tools/metrics` on the day and read out those numbers.** E18 is a snapshot from 19:56 UTC on 2026-11-14.
- **The drill footage:** if the 18:20 drill wasn't screen-recorded, re-create it the same way. File a clearly marked `[DRILL]` issue with the `escape` label and an `Introduced-by: #N` line in the body, where #N is a PR that touches the area of an open PR being filmed. Wait for `trust` to fail, then close it and remove the `escape` label. Announce it on the board first, as before **[E19]**.
- **Don't claim time saved:** there is no baseline **[E19]**.
- **Don't blur faces or names into the AI's work:** each PR shows its human owner, and that is the point.

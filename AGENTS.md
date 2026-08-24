# TOBI Rules For Codex

This file applies to source-code work in this checkout. The workspace root is
`D:\[PERSONAL PROJECT FILES]\TOBI`; source changes belong here, not in
`tobi-codex`.

## Start Every Code Task

1. Read `CLAUDE.md` for the complete TOBI engineering rules.
2. Read `.claude/CURRENT_WORK.md`. Its purpose, non-goals, expected files, and
   gate define the active package. If it says `Gate: no`, this is not an
   implementation package yet.
3. Read `docs/README.md`, then the relevant current-state and architecture
   documents before deciding that a plan or queue item matches the code.
4. Use `graphify-out/` only as a navigation map. Verify every important finding
   in current code and tests because the graph can be older than the checkout.
5. When the owner says `SIMPLE RESULT VN TM2`, follow
   `docs/SIMPLE_RESULT_VN_TM02.md` and give the current result in brief, plain
   Vietnamese while keeping useful technical terms in English.

## Work Safely

- Preserve unrelated local changes. Do not use `tobi-codex`.
- Do not use Supabase or Vercel without the owner's confirmation for this task.
- Do not run `main.py start` during normal development. It starts Telegram and
  scheduled work. Use the focused commands in `docs/DEVELOPMENT.md` instead.
- A change is not complete until `python scripts/gate.py` passes when the active
  package has a green gate. The Codex stop hook also runs this check.
- For any UI change, provide build or browser evidence and preserve the shared
  async loading behavior.
- Update current documents and the queue row when delivered behavior changes.

## Working Shape

Keep one package small enough to review: one outcome, explicit non-goals,
expected files, focused checks, and an owner decision before merge or deploy.
Use separate read-only workers for independent exploration, test analysis, or
review. Do not let parallel workers edit the same subsystem.

# SIMPLE RESULT VN TM2

## Purpose

`SIMPLE RESULT VN TM2` is TOBI's agent-neutral simplification protocol. Any
agent can use it when a result has too much context, research, discussion, or
technical detail for the owner to read quickly.

`TM2` is the protocol name, not a queue item and not a code version.

## Trigger

Run this protocol when the owner says:

- `SIMPLE RESULT VN TM2`
- `Use SIMPLE RESULT VN TM2`
- `Give me the simple Vietnamese result`
- `Simplify this in Vietnamese`

Also use it when the owner asks for a shorter Vietnamese explanation after a
large research, discussion, review, planning, or reporting task.

## Action

Present the current result in Vietnamese that is brief, plain, and easy to
follow. Keep technical or scientific terms in English when that makes the
meaning clearer.

The goal is that a non-technical person can read it, understand what matters,
and stay connected to the context without needing to read the full technical
work.

## Use When

Use TM2 for:

- research results with many facts or sources;
- technical discussions that need an owner-friendly summary;
- progress reports with many implementation details;
- planning or review output that needs a simpler decision view;
- any long answer where the owner asks for Vietnamese simplification.

Do not use TM2 to hide uncertainty, failed checks, missing evidence, or risks.
If something is not verified, say that plainly in Vietnamese.

## Output Rules

1. Start with the main result in one short sentence.
2. Use Vietnamese for explanation, but keep useful English terms such as
   `API`, `runtime`, `schema`, `database`, `model`, `token`, `frontend`,
   `backend`, `test`, or scientific terms.
3. Use short sections or a small table when it helps scanning.
4. Keep the answer brief. Remove background that does not change the owner's
   decision.
5. Explain technical terms by what they do the first time they appear.
6. End with what the owner can do next, or what is blocked.

## Suggested Shape

```markdown
**Ket qua:** ...

| Muc | Noi dung ngan gon |
|---|---|
| Dieu da biet | ... |
| Dieu quan trong | ... |
| Rui ro / chua chac | ... |
| Viec tiep theo | ... |
```

Use Vietnamese accents in final owner-facing output when the environment
supports them. The ASCII template above is only a fallback for agents or tools
that cannot safely emit accents.

## Safety Rules

- Do not change facts while simplifying.
- Do not omit blockers or failed checks.
- Do not translate code identifiers, file names, commands, model names, API
  names, or product names.
- Do not add new claims that were not present in the current result or verified
  evidence.
- Do not interact with Supabase, Vercel, or external services just to simplify
  a report.

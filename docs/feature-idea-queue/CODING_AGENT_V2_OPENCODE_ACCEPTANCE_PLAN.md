# Coding Agent V2 - OpenCode acceptance fixture

## Objective

Prove that the OpenCode developer agent can complete one small, concrete Queue item
through the durable Coding Agent V2 workflow while preserving the selected provider
and model identity.

## Scope

Create one file only:

`docs/acceptance/coding-agent-v2-opencode-run.md`

The file must contain:

- A level-one heading named `Coding Agent V2 OpenCode Run`
- The exact marker `OPENCODE_ACCEPTANCE=ready`
- A short statement that this artifact was created by the OpenCode matrix run

Do not modify any existing file.

## Acceptance Criteria

- Must create `docs/acceptance/coding-agent-v2-opencode-run.md` and no other file
- Must include the exact marker `OPENCODE_ACCEPTANCE=ready`
- Must identify OpenCode and the selected provider/model in the acceptance artifact

## Dependencies

- Queue item #22 final qualification implementation must be running locally
- OpenCode and the independent reviewer must both report Ready in Developer Agents

## Delivery Notes

- Select `OpenCode + GLM` explicitly during preflight.
- Keep Auto off.
- Verify the same provider and model remain visible in Process and History.
- Completion requires criterion evidence, a scorecard, a pushed branch, and a draft PR.
- Merge remains owner-controlled on GitHub under the default reviewed policy.

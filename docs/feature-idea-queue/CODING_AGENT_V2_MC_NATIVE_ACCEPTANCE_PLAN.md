# Coding Agent V2 - MC Native acceptance fixture

## Objective

Prove that the MC Native developer agent can complete one small, concrete Queue item
through the durable Coding Agent V2 workflow. This fixture tests the workflow, not
TOBI product behavior.

## Scope

Create one file only:

`docs/acceptance/coding-agent-v2-mc-native-run.md`

The file must contain:

- A level-one heading named `Coding Agent V2 MC Native Run`
- The exact marker `MC_NATIVE_ACCEPTANCE=ready`
- A short statement that this artifact was created by the MC Native matrix run

Do not modify any existing file.

## Acceptance Criteria

- Must create `docs/acceptance/coding-agent-v2-mc-native-run.md` and no other file
- Must include the exact marker `MC_NATIVE_ACCEPTANCE=ready`
- Must identify MC Native as the agent used for this acceptance artifact

## Dependencies

- Queue item #22 final qualification implementation must be running locally
- MC Native and the independent reviewer must both report Ready in Developer Agents

## Delivery Notes

- Select `MC Native` explicitly during preflight.
- Keep Auto off.
- Completion requires criterion evidence, a scorecard, a pushed branch, and a draft PR.
- Merge remains owner-controlled on GitHub under the default reviewed policy.

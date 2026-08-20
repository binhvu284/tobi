# Mission Control V2 Legacy Exit Review

**Decision: deferred.** Queue #21 does not delete any legacy execution path.

The Runtime V2 contracts, durable run history, security controls, Runs page, staged rollout, and
compatibility adapters are delivered. Projects, Office, CLI, Telegram, and scheduler work still
executes through the existing owners while the adapter records bounded shadow evidence.

Legacy retirement requires a separate owner-approved queue item. That review must prove production
parity for every surface, completed rollback drills, retained history, current backups, and zero
open high-severity evaluation findings before any code or table is removed.

Until that decision, legacy behavior remains the rollback path and is not technical debt authorized
for opportunistic deletion.

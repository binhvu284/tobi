# Awakening external read requires verified test evidence

## Objective
`awakening._connector_states()` marks a read connector **verified** when the integration
object's `is_available()` returns True. For GitHub that method is `return bool(self.token)`
— presence only — so any non-empty `GITHUB_TOKEN`, including a dummy or revoked one, is
promoted to verified and `_eval_external_read()` reports `external_read_access = "active"`.
The connector's own `test()` method does make a live API call, but this path never calls it.

Awakening should not claim an ability from credential presence alone.
`tests/test_awakening.py` already asserts the correct result and fails today because of
this gap; the assertion is right and the code is wrong.

Observed in a clean run:

    GITHUB_TOKEN unset         ->  setup_needed   (correct)
    GITHUB_TOKEN="ghp_dummy"   ->  active         (wrong; expected partial)

## Scope
Change `core/awakening.py`, specifically `_connector_states()` and the docstring stating the
incorrect rule. Touch `tests/test_awakening.py` only if a new case is needed; leave the
existing configured-but-unverified expectation exactly as written.

## Acceptance Criteria
- Must treat a read connector as verified only when a successful connection test proves it, not when a token is merely present
- Must report external read access as partial when credentials exist without successful test evidence, and as setup needed when no connector is configured
- Must leave tests/test_awakening.py fully green with its configured-but-unverified expectation unchanged

## Dependencies
- None

## Goal Links
- None

## Delivery Notes
- Start only after strict Developer preflight succeeds.
- Completion requires deterministic checks, criterion evidence, and independent review.
- Verify with `python tests/test_awakening.py` and `python tests/test_awakening_route.py`.

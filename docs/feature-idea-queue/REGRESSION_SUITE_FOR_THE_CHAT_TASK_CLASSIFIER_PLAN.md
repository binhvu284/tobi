# Regression suite for the chat task classifier

## Objective
`core/task_classifier.py` exposes one pure function, `classify(text)`, which returns one of
SMALLTALK, CODING, RESEARCH, STATUS, EXECUTION, PROJECT_MGMT or QUESTION. It routes chat
turns and the Telegram handler, it has no test file of its own, and its behaviour depends on
a precedence order that is easy to break by reordering a single branch.

Two rules in particular are unguarded today:

1. SMALLTALK only applies to text shorter than 60 characters, so a long message that opens
   with a greeting falls through to a later category.
2. The CODING check runs before the PROJECT_MGMT check, so a message containing both a
   coding word and a project word returns CODING.

Add a self-contained regression suite that locks the seven outcomes and both ordering rules
in place.

## Scope
Create one new file, `tests/test_task_classifier.py`. Do not modify `core/task_classifier.py`
or any other existing file.

Match the house test style used elsewhere in `tests/`: a plain script with no pytest, an
`ok(name, condition, detail)` helper that prints a line per check and exits non-zero on the
first failure, and a final summary line reporting the number of checks that ran. The suite
imports `classify` directly and needs no environment, no temporary store and no network.

Use ASCII-only inputs. The English patterns already reach all seven outcomes, for example
"hello" for SMALLTALK, "write a script" for CODING, "find a niche" for RESEARCH, "revenue
report" for STATUS, "execute the plan" for EXECUTION, "list projects" for PROJECT_MGMT, and
"what is the capital of France" for QUESTION.

## Acceptance Criteria
- Must add tests/test_task_classifier.py with at least one ASCII-only case for each of the seven classify outcomes
- Must include a case proving the 60-character smalltalk limit and a case proving a coding word outranks a project word
- Must leave the new suite green under `python tests/test_task_classifier.py` while every existing file stays byte-identical

## Dependencies
- None

## Goal Links
- None

## Delivery Notes
- Start only after strict Developer preflight succeeds.
- Completion requires deterministic checks, criterion evidence, and independent review.
- Verify with `python tests/test_task_classifier.py`.

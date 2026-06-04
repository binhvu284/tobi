"""Environment loading helpers.

Keeps startup resilient when python-dotenv is not installed.
"""


def safe_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    load_dotenv()

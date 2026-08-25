"""Fast task classifier — no LLM, pure regex. Used for routing in handle_chat."""
import re
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from core.runtime.workflows import WorkflowSelection

_SMALLTALK = [
    r"^(hi|hello|hey|yo)\b",
    r"^(xin chào|chào|alo)\b",
    r"^(ok|oke|okay|được rồi|good|got it|rồi)\b",
    r"^(cảm ơn|thanks|thank you|thks|ty)\b",
    r"^(bye|tạm biệt|hẹn gặp)\b",
    r"^(bạn khỏe|how are you|mày khỏe)\b",
    r"^tobi[,!?.]?\s*$",
]

_CODING = [
    r"\bcode\b", r"\bscript\b", r"\bviết.*?code\b", r"\bimplement\b",
    r"\brefactor\b", r"\bdebug\b", r"\bfix.*?bug\b", r"\bbuild.*?app\b",
    r"\bcreate.*?file\b", r"\bapi.*?endpoint\b", r"\bfunction\b.*?\bdef\b",
    r"\bviết.*?hàm\b", r"\btạo.*?file\b", r"\bsửa.*?lỗi\b",
]

_RESEARCH = [
    r"\bresearch\b", r"\bniche\b", r"\bcơ hội\b", r"\btìm.*?kiếm\b",
    r"\bmarket.*?analysis\b", r"\bcompetitor\b", r"\banalyz\b",
    r"\btìm.*?niche\b", r"\bopportunity\b",
]

_STATUS = [
    r"\bstatus\b", r"\brevenue\b", r"\bdoanh thu\b", r"\bportfolio\b",
    r"\bprogress\b", r"\btiến độ\b", r"\btổng quan\b", r"\bsummary\b",
    r"\breport\b", r"\bthống kê\b", r"\bhow.*?doing\b", r"\bđang.*?làm\b",
]

_EXECUTION = [
    r"\bexecute\b", r"\bdeploy\b", r"\bchạy\b", r"\bthực thi\b",
    r"\brun.*?task\b", r"\bstart.*?project\b",
]

_PROJECT_MGMT = [
    r"\bcreate\s+project\b", r"\bnew\s+project\b", r"\btạo\s+project\b", r"\btạo\s+dự án\b",
    r"\badd\s+task\b", r"\bthêm\s+task\b", r"\bthêm\s+nhiệm vụ\b",
    r"\bupdate\s+(goal|progress|task)\b", r"\bcập nhật\s+(goal|tiến độ|task)\b",
    r"\bmark.*?done\b", r"\bcomplete\s+task\b", r"\bhoàn thành\s+task\b",
    r"\bproject\s+status\b", r"\blist\s+projects?\b", r"\bmy\s+projects?\b",
    r"\bproject\s+tasks?\b", r"\bproject\s+goals?\b",
    r"\bdự án\b",
]


def classify(text: str) -> str:
    """Return SMALLTALK | CODING | RESEARCH | STATUS | EXECUTION | PROJECT_MGMT | QUESTION"""
    t = text.strip()
    tl = t.lower()

    if len(t) < 60 and any(re.search(p, tl) for p in _SMALLTALK):
        return "SMALLTALK"
    if any(re.search(p, tl) for p in _CODING):
        return "CODING"
    if any(re.search(p, tl) for p in _PROJECT_MGMT):
        return "PROJECT_MGMT"
    if any(re.search(p, tl) for p in _RESEARCH):
        return "RESEARCH"
    if any(re.search(p, tl) for p in _STATUS):
        return "STATUS"
    if any(re.search(p, tl) for p in _EXECUTION):
        return "EXECUTION"
    return "QUESTION"


def classify_workflow(
    text: str, fields: Mapping[str, Any] | None = None,
) -> "WorkflowSelection":
    """Select a frozen supported workflow without invoking a model."""
    from core.runtime.workflows import supported_workflow_catalog

    return supported_workflow_catalog().select(text, fields)

"""Fast task classifier — no LLM, pure regex. Used for routing in handle_chat."""
import re

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


def classify(text: str) -> str:
    """Return task type: SMALLTALK | CODING | RESEARCH | STATUS | EXECUTION | QUESTION"""
    t = text.strip()
    tl = t.lower()

    if len(t) < 60 and any(re.search(p, tl) for p in _SMALLTALK):
        return "SMALLTALK"
    if any(re.search(p, tl) for p in _CODING):
        return "CODING"
    if any(re.search(p, tl) for p in _RESEARCH):
        return "RESEARCH"
    if any(re.search(p, tl) for p in _STATUS):
        return "STATUS"
    if any(re.search(p, tl) for p in _EXECUTION):
        return "EXECUTION"
    return "QUESTION"

"""
Text-processing utilities for the action-items extractor Lambda.

Ported from the workspace text_processing.py. Steering-file alias machinery
is intentionally omitted; canonical_owner() uses _OWNER_ALIASES_FALLBACK only.
"""

import html
import re
from datetime import datetime, timedelta, date

# ─── Compiled Regex Patterns ─────────────────────────────────────────────────

# Extract tasks from Confluence storage format
TASK_RE = re.compile(
    r"<ac:task>"
    r"(?:<ac:task-id>(.*?)</ac:task-id>)?"
    r".*?<ac:task-status>(.*?)</ac:task-status>"
    r".*?<ac:task-body>(.*?)</ac:task-body>"
    r".*?</ac:task>",
    re.DOTALL,
)

# Confluence user mention tags
USER_MENTION_RE = re.compile(
    r'<ac:link>\s*<ri:user\s+ri:account-id="([^"]+)"[^/]*/>\s*</ac:link>'
)

# Generic HTML tag stripper
HTML_TAG_RE = re.compile(r"<[^>]+>")

# Whitespace normalizer
_WHITESPACE_RE = re.compile(r"\s+")

# Date from meeting-notes title (M.DD.YYYY prefix)
DATE_TITLE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})")

# ─── Owner extraction patterns ───────────────────────────────────────────────

_OWNER_RE = re.compile(r"^@([\w\s]+?)(?:\s*[-\u2013\u2014,]|\s+will\s|\s+and\s+@|\s+&)")

# Repair for the newer Confluence editor's task serialization, which wraps task
# bodies in <span class="placeholder-inline-tasks"> and drops the space between
# the owner mention and the following verb, e.g. "@Tiffany Christensenwill …".
_GLUED_OWNER_WILL_RE = re.compile(r"^(@[\w][\w\s]*?[a-z])(will\s)")

_INVALID_OWNERS = frozenset({
    "will", "and", "the", "a", "an", "to", "for", "with", "on", "in", "at"
})

# ─── Owner canonicalization ──────────────────────────────────────────────────

_OWNER_ALIASES_FALLBACK = {
    "nick": "Nick Bernard",
    "nick bernard": "Nick Bernard",
    "adam": "Adam Phillipps",
    "adam phillipps": "Adam Phillipps",
    "hayes": "Hayes Hicken",
    "hayes hicken": "Hayes Hicken",
    "scott": "Scott Lewis",
    "scott lewis": "Scott Lewis",
    "tiffany": "Tiffany Christensen",
    "tiffany christensen": "Tiffany Christensen",
    "jesse": "Jesse Phillipps",
    "jesse phillipps": "Jesse Phillipps",
    "steve": "Steve Peters",
    "steve peters": "Steve Peters",
    "giovanni": "Giovanni Molina Santiago",
    "giovanni molina santiago": "Giovanni Molina Santiago",
}


def canonical_owner(owner: str) -> str:
    """Collapse first-name/full-name variants to one canonical owner name.

    Uses _OWNER_ALIASES_FALLBACK only (no steering-file loading in Lambda).
    Unknown owners are returned unchanged. Matching is case-insensitive.
    """
    if not owner:
        return owner
    return _OWNER_ALIASES_FALLBACK.get(owner.strip().lower(), owner)


# ─── Strip patterns ──────────────────────────────────────────────────────────

_STRIP_PATTERNS = (
    re.compile(r"^@[\w\s]+?\s+and\s+@[\w\s]+?\s+[-\u2013\u2014]\s+"),
    re.compile(r"^@[\w\s]+?\s+will\s+"),
    re.compile(r"^@[\w\s]+?\s+[-\u2013\u2014]\s+"),
    re.compile(r"^All\s+team\s+members\s+[-\u2013\u2014]\s+", re.IGNORECASE),
    re.compile(r"^All\s+team\s+members\s+will\s+", re.IGNORECASE),
)

# ─── Priority extraction patterns ────────────────────────────────────────────

_PRIORITY_TAG_RE = re.compile(
    r"\[(?P<tag>HIGH|MEDIUM|LOW|P1|P2|P3|URGENT|CRITICAL)\]",
    re.IGNORECASE,
)

_PRIORITY_MAP = {
    "high": "high", "p1": "high", "urgent": "high", "critical": "high",
    "medium": "medium", "p2": "medium",
    "low": "low", "p3": "low",
}

# ─── Due date extraction patterns ────────────────────────────────────────────

_DUE_DATE_EXPLICIT_RE = re.compile(
    r"(?:by|due|deadline[:\s]*)\s*"
    r"(?:(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?|"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+(\d{1,2})(?:[,\s]+(\d{4}))?)",
    re.IGNORECASE,
)

_DUE_DATE_RELATIVE_RE = re.compile(
    r"\b(?:by\s+)?(?P<rel>this\s+week|next\s+week|end\s+of\s+(?:week|sprint)|"
    r"EOW|EOD|today|tomorrow|"
    r"next\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))\b",
    re.IGNORECASE,
)

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_DAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# ─── Blocked-by patterns ─────────────────────────────────────────────────────

_BLOCKED_BY_RE = re.compile(
    r"(?:blocked\s+by|waiting\s+on|depends\s+on|pending\s+input\s+from)\s+@?([\w]+(?:\s+[\w]+)?)"
    r"(?:\s+(?:for|to|about|on|regarding|re:)\b|[,;.\-\u2013\u2014]|\s*$)",
    re.IGNORECASE,
)

# Secondary owners: "@Owner1 and @Owner2 will ..." or "@Owner1 & @Owner2 - ..."
_SECONDARY_OWNER_RE = re.compile(
    r"^@[\w\s]+?\s+(?:and|&)\s+@([\w\s]+?)(?:\s*[-\u2013\u2014,]|\s+will\s)",
)


# ─── Core Functions ──────────────────────────────────────────────────────────


def normalize_task_text(html_text: str, resolve_user=None) -> str:
    """Convert task body HTML to canonical plain text.

    Args:
        html_text: Raw HTML from a Confluence <ac:task-body> element.
        resolve_user: Optional callable(account_id: str) -> str that resolves
                      Confluence account IDs to display names. If None, user
                      mentions are stripped silently.

    Returns:
        Cleaned, whitespace-normalized plain text.
    """
    if not html_text:
        return ""

    text = html_text

    if resolve_user is not None:
        def _replace(m):
            name = resolve_user(m.group(1))
            return f"@{name} " if name else ""
        text = USER_MENTION_RE.sub(_replace, text)
    else:
        text = USER_MENTION_RE.sub("", text)

    text = HTML_TAG_RE.sub("", text)
    text = html.unescape(text)

    if "\u2014" in text or "\u2013" in text:
        text = text.replace("\u2014", " - ").replace("\u2013", " - ")
    text = _WHITESPACE_RE.sub(" ", text).strip()

    if text.startswith("@"):
        text = _GLUED_OWNER_WILL_RE.sub(r"\1 \2", text, count=1)
    return text


def extract_owner(text: str) -> str:
    """Extract the @-mentioned owner from action item text.

    Returns:
        The owner's name, "All team members", or "Unassigned".
    """
    if not text:
        return "Unassigned"
    m = _OWNER_RE.match(text)
    if m:
        name = m.group(1).strip()
        first_word = name.split()[0].lower() if name else ""
        if first_word not in _INVALID_OWNERS and len(name) > 1:
            return name
    if text[:4].lower() == "all ":
        return "All team members"
    return "Unassigned"


def extract_priority(text: str) -> str:
    """Extract priority level from action item text.

    Returns:
        "high", "medium", "low", or "" (unset).
    """
    m = _PRIORITY_TAG_RE.search(text)
    if m:
        tag = m.group("tag").lower()
        return _PRIORITY_MAP.get(tag, "")

    lower = text.lower()
    if "asap" in lower or "immediately" in lower or "urgent" in lower or "critical" in lower or "blocker" in lower:
        return "high"
    return ""


def extract_due_date(text: str, reference_date: date = None) -> str:
    """Extract a due date from action item text.

    Returns:
        ISO date string (YYYY-MM-DD) or "".
    """
    if reference_date is None:
        reference_date = date.today()

    m = _DUE_DATE_EXPLICIT_RE.search(text)
    if m:
        if m.group(1):
            month = int(m.group(1))
            day = int(m.group(2))
            year = int(m.group(3)) if m.group(3) else reference_date.year
            if year < 100:
                year += 2000
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                pass
        elif m.group(4):
            month_name = m.group(4).lower()
            month = _MONTH_MAP.get(month_name, 0)
            day = int(m.group(5))
            year = int(m.group(6)) if m.group(6) else reference_date.year
            if month:
                try:
                    return date(year, month, day).isoformat()
                except ValueError:
                    pass

    m = _DUE_DATE_RELATIVE_RE.search(text)
    if m:
        rel = m.group("rel").lower().strip()
        if rel in ("today", "eod"):
            return reference_date.isoformat()
        elif rel == "tomorrow":
            return (reference_date + timedelta(days=1)).isoformat()
        elif rel in ("this week", "end of week", "eow", "end of sprint"):
            days_until_friday = (4 - reference_date.weekday()) % 7
            if days_until_friday == 0 and reference_date.weekday() > 4:
                days_until_friday = 7
            return (reference_date + timedelta(days=days_until_friday or 7)).isoformat()
        elif rel == "next week":
            days_until_friday = (4 - reference_date.weekday()) % 7
            return (reference_date + timedelta(days=days_until_friday + 7)).isoformat()
        elif rel.startswith("next "):
            day_name = rel.split()[-1]
            target_day = _DAY_MAP.get(day_name, -1)
            if target_day >= 0:
                days_ahead = (target_day - reference_date.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                return (reference_date + timedelta(days=days_ahead)).isoformat()

    return ""


def extract_blocked_by(text: str) -> str:
    """Extract the person/entity blocking this action item.

    Returns:
        The blocking person's name, or "".
    """
    m = _BLOCKED_BY_RE.search(text)
    if m:
        name = m.group(1).strip()
        if name and len(name) > 1:
            return name
    return ""


def extract_secondary_owners(text: str) -> list:
    """Extract secondary/collaborative owners from action item text.

    Returns:
        List of secondary owner names (may be empty).
    """
    m = _SECONDARY_OWNER_RE.match(text)
    if m:
        name = m.group(1).strip()
        if name and name.split()[0].lower() not in _INVALID_OWNERS:
            return [name]
    return []


def extract_date_object_from_title(title: str) -> date:
    """Extract a date object from a meeting-notes page title.

    Input:  "5.27.2026 - Topic Name"
    Output: date(2026, 5, 27)

    Returns None if no date can be parsed.
    """
    m = DATE_TITLE_RE.match(title)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass
    return None


def extract_date_from_title(title: str) -> str:
    """Extract a formatted date string from a meeting-notes page title.

    Input:  "5.27.2026 - Topic Name"
    Output: "May 27, 2026"
    """
    m = DATE_TITLE_RE.match(title)
    if m:
        try:
            dt = datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)))
            return dt.strftime("%B %d, %Y")
        except ValueError:
            pass
    return ""


def compute_item_age(created_date: str, reference_date: date = None) -> int:
    """Compute the age of an item in days.

    Args:
        created_date: Formatted date string like "May 27, 2026" or ISO "2026-05-27".
        reference_date: Date to compute age against (defaults to today).

    Returns:
        Number of days since creation, or -1 if date can't be parsed.
    """
    if not created_date:
        return -1

    if reference_date is None:
        reference_date = date.today()

    try:
        created = date.fromisoformat(created_date)
        return (reference_date - created).days
    except (ValueError, TypeError):
        pass

    try:
        dt = datetime.strptime(created_date, "%B %d, %Y")
        return (reference_date - dt.date()).days
    except (ValueError, TypeError):
        pass

    return -1


def age_bucket(days: int) -> str:
    """Classify item age into a bucket for display.

    Returns:
        "fresh" (0-7 days), "aging" (8-14 days), "stale" (15-30 days),
        "critical" (>30 days), or "unknown" if days < 0.
    """
    if days < 0:
        return "unknown"
    if days <= 7:
        return "fresh"
    if days <= 14:
        return "aging"
    if days <= 30:
        return "stale"
    return "critical"


def extract_tasks_from_body(html_body: str, page_title: str = "") -> list:
    """Extract all tasks from a Confluence page body.

    Returns list of dicts with keys: status, text, priority, due_date,
    blocked_by, secondary_owners.
    resolve_user is not used in Lambda context (user mentions become empty).
    """
    ref_date = extract_date_object_from_title(page_title)
    tasks = []
    for match in TASK_RE.finditer(html_body):
        status = match.group(2).strip()
        body_html = match.group(3).strip()
        text = normalize_task_text(body_html)  # no resolve_user in Lambda
        if text:
            tasks.append({
                "status": status,
                "text": text,
                "priority": extract_priority(text),
                "due_date": extract_due_date(text, reference_date=ref_date),
                "blocked_by": extract_blocked_by(text),
                "secondary_owners": extract_secondary_owners(text),
            })
    return tasks

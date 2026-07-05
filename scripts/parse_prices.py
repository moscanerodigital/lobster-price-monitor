"""Price parsing — pure function, easily testable.

Strategy: for each $/lb price in the text, look LEFT for the nearest tier
keyword (e.g. "chicks", "old shell") and assign that tier. This is the
dominant FB-post style: "Chicks 1 1/4 lb $8.75, Old Shell $10.75, ..."

Outputs: list of (kind, key, price, unit, raw_snippet) tuples.
  - kind "lobster_tier": live lobster $/lb, canonical tier name, unit "lb"
  - kind "oyster_tier":  oysters $/doz, canonical size/grade, unit "doz"
  - kind "special":      any other seafood item or non-live lobster product
"""
from __future__ import annotations
import re
from typing import Literal

# ---- Lobster tier keywords (more specific first) ----
_TIER_KEYWORDS: list[tuple[str, str]] = [
    (r"\b(?:chicks|chix)\b", "chicks"),
    (r"\b(?:soft\s*shell|softshell)\b", "soft_shell"),
    (r"\b(?:old\s*shell|oldshell)\b", "old_shell"),
    (r"\b(?:hard\s*shell|hardshell)\b", "hard_shell"),
    (r"\b(?:firm\s*shell|firm)\b", "hard_shell"),
    (r"\b(?:select|selects)\b", "select"),
    (r"(?:2\s*lb\s*(?:and|or|&)\s*(?:up|\+|plus)|2\s*lb\s*plus|2lb\+|2\s*pound\s*plus|\bjumbo)", "2lb_plus"),
    (r"(?:1\s*⅛|1\.125)\s*lb", "1.125lb"),
    (r"(?:1\s*¼|1\.25|1\s*1/4)\s*lb", "1.25lb"),
    (r"(?:1\s*½|1\.5|1\s*1/2)\s*lb", "1.5lb"),
    (r"(?:1\s*¾|1\.75|1\s*3/4)\s*lb", "1.75lb"),
]

_OYSTER_TIER_KEYWORDS: list[tuple[str, str]] = [
    (r"\b(?:single\s*selects?)\b", "single_select"),
    (r"\b(?:extra\s*large|xl)\b", "xl"),
    (r"\b(?:jumbos?)\b", "jumbo"),
    (r"\b(?:selects?)\b", "select"),
    (r"\b(?:standards?)\b", "standard"),
    (r"\b(?:pints?)\b", "pint"),
    (r"\b(?:wellfleet|wells|belon|blue\s*points?|kumamotos?|malaquite|beausoleils?|moonstones?|pearl\s*points?|savage\s*blondes?)\b", "named_variety"),
    (r"\b(?:small|petite|pearl)\b", "small"),
    (r"\b(?:medium)\b", "medium"),
    (r"\b(?:large)\b", "large"),
]

_PRICE_LB_RE = re.compile(
    r"\$\s*(\d+(?:\.\d+)?)\s*"
    r"(?:"
    r"/\s*lb"
    r"|per\s*pound"
    r"|a\s*pound"
    r"|\s*lb\b"
    r"|/\s*pound"
    r")",
    re.IGNORECASE,
)
_PRICE_DOZ_RE = re.compile(
    r"\$\s*(\d+(?:\.\d+)?)\s*"
    r"(?:"
    r"/\s*doz"
    r"|per\s*dozen"
    r"|a\s*dozen"
    r"|/\s*dz"
    r"|\s*dz\b"
    r"|\s*doz\b"
    r"|\s*dozen"
    r")",
    re.IGNORECASE,
)
_PRICE_EA_RE = re.compile(
    r"\$\s*(\d+(?:\.\d+)?)\s*"
    r"(?:"
    r"each"
    r"|/\s*ea\b"
    r"|/\s*roll"
    r"|per\s*roll"
    r"|ea\b"
    r")",
    re.IGNORECASE,
)
# Bare $X.XX — only when context implies a price (no unit suffix)
_PRICE_BARE_RE = re.compile(r"\$\s*(\d+(?:\.\d+)?)(?!\s*(?:/|per|\s*(?:lb|doz|dz|ea|each|roll)\b))", re.IGNORECASE)

_SPECIAL_KEYWORDS = [
    "halibut", "scallops", "clams", "shrimp",
    "haddock", "salmon", "cod", "pollock", "tuna", "swordfish",
    "chowder", "bisque", "roll", "mac", "bake", "ravioli",
    "scallop", "clam", "crab",
    "smoked", "stew",
]

# AC4b specials post detection keywords
SPECIALS_POST_KEYWORDS = [
    "halibut", "scallops", "clams", "shrimp",
    "haddock", "salmon", "chowder", "roll",
]

_CANONICAL_SPECIAL_MAP: list[tuple[str, str]] = [
    (r"\blobster\s*rolls?\b", "lobster_roll"),
    (r"\bclam\s*chowder\b", "chowder"),
    (r"\blobster\s*mac\b", "mac"),
    (r"\bhalibut\b", "halibut"),
    (r"\bscallops?\b", "scallops"),
    (r"\bclams?\b", "clams"),
    (r"\bshrimp\b", "shrimp"),
    (r"\bhaddock\b", "haddock"),
    (r"\bsalmon\b", "salmon"),
    (r"\bcod\b", "cod"),
    (r"\bpollock\b", "pollock"),
    (r"\btuna\b", "tuna"),
    (r"\bswordfish\b", "swordfish"),
    (r"\bchowder\b", "chowder"),
    (r"\bbisque\b", "bisque"),
    (r"\brolls?\b", "roll"),
    (r"\bcrab\b", "crab"),
    (r"\bsmoked\b", "smoked"),
    (r"\bstew\b", "stew"),
    (r"\bmac\b", "mac"),
    (r"\bbake\b", "bake"),
    (r"\bravioli\b", "ravioli"),
]

ParsedRow = tuple[Literal["lobster_tier", "oyster_tier", "special"], str, float, str, str]
ParseMeta = dict


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s[:80]


def _canonical_special_key(clause: str, kw: str | None) -> str:
    clause_l = clause.lower()
    for pattern, canonical in _CANONICAL_SPECIAL_MAP:
        if re.search(pattern, clause_l, re.IGNORECASE):
            return canonical
    if kw:
        if kw == "roll" and "lobster" in clause_l:
            return "lobster_roll"
        return kw
    return _slug(clause)[:40] or "special"


def _clause_of(text: str, pos: int) -> str:
    """Return the clause containing pos, delimited by comma, semicolon, '. ', or ' and '."""
    and_start = -1
    search_from = 0
    while True:
        idx = text.lower().find(" and ", search_from, pos)
        if idx < 0:
            break
        and_start = idx + 5
        search_from = idx + 5
    comma = text.rfind(",", 0, pos)
    semi = text.rfind(";", 0, pos)
    dot = text.rfind(". ", 0, pos)
    start = max(comma, semi, dot, and_start)
    if start >= 0:
        if start == and_start:
            return text[start:pos]
        return text[start + 1:pos]
    return text[max(0, pos - 60):pos]


def _find_tier_left_of(text: str, price_pos: int) -> str | None:
    size_tiers = {"1.125lb", "1.25lb", "1.5lb", "1.75lb", "2lb_plus"}
    window_start = max(0, price_pos - 160)
    left = text[window_start:price_pos]

    boundaries: list[int] = []
    for i, ch in enumerate(left):
        if ch in (",", ";"):
            boundaries.append(i)
    for i in range(len(left) - 2, -1, -1):
        if left[i] == "." and left[i + 1] == " ":
            if i > 0 and left[i - 1].isdigit():
                continue
            boundaries.append(i)
    boundaries.sort()

    if not boundaries:
        clauses = [(0, len(left))]
    else:
        clauses = []
        start = 0
        for b in boundaries:
            clauses.append((start, b))
            start = b + 1
        clauses.append((start, len(left)))

    current_clause = clauses[-1]
    prev_clause = clauses[-2] if len(clauses) >= 2 else None

    def _tiers_in_clause(cl: tuple[int, int]) -> list[tuple[int, str]]:
        cs, ce = cl
        cands: list[tuple[int, str]] = []
        seg = left[cs:ce]
        for pattern, canonical in _TIER_KEYWORDS:
            for m in re.finditer(pattern, seg, re.IGNORECASE):
                cands.append((m.start() + cs, canonical))
        return cands

    same = _tiers_in_clause(current_clause)
    if same:
        non_size = [c for c in same if c[1] not in size_tiers]
        if non_size:
            non_size.sort(key=lambda c: -c[0])
            return non_size[0][1]
        same.sort(key=lambda c: -c[0])
        return same[0][1]

    if prev_clause is not None:
        prev = _tiers_in_clause(prev_clause)
        prev_size = [c for c in prev if c[1] in size_tiers]
        if prev_size:
            prev_size.sort(key=lambda c: -c[0])
            return prev_size[0][1]
    return None


def _find_oyster_grade_in_clause(clause: str) -> str | None:
    matches: list[tuple[int, str]] = []
    for pattern, canonical in _OYSTER_TIER_KEYWORDS:
        m = re.search(pattern, clause, re.IGNORECASE)
        if m:
            matches.append((m.start(), canonical))
    if not matches:
        return None
    grades = [c for _, c in matches if c != "named_variety"]
    if grades:
        leftmost = min((m for m in matches if m[1] != "named_variety"), key=lambda x: x[0])
        return leftmost[1]
    leftmost = min(matches, key=lambda x: x[0])
    return leftmost[1]


def _find_special_kw(text: str, around_pos: int) -> str | None:
    s = max(0, around_pos - 80)
    e = min(len(text), around_pos + 30)
    window = text[s:e].lower()
    for kw in _SPECIAL_KEYWORDS:
        if kw in window:
            return kw
    return None


def _find_special_kw_in_clause(text: str, price_pos: int) -> str | None:
    clause = _clause_of(text, price_pos).lower()
    # Prefer longer/more specific matches first
    for kw in sorted(_SPECIAL_KEYWORDS, key=len, reverse=True):
        if kw in clause:
            return kw
    return None


def _clause_has_lobster_tier(text: str, price_pos: int) -> bool:
    clause = _clause_of(text, price_pos)
    for pattern, _canonical in _TIER_KEYWORDS:
        if re.search(pattern, clause, re.IGNORECASE):
            return True
    return "lobster" in clause.lower()


def _clause_has_special_only(text: str, price_pos: int) -> bool:
    """True when clause has a special keyword but no live-lobster tier context."""
    clause_l = _clause_of(text, price_pos).lower()
    has_special = any(kw in clause_l for kw in _SPECIAL_KEYWORDS)
    if not has_special:
        return False
    return not _clause_has_lobster_tier(text, price_pos)


def _infer_unit_from_clause(clause: str) -> str:
    cl = clause.lower()
    if any(x in cl for x in ("roll", "each", "dinner", "/ea", " per ea")):
        return "ea"
    if any(x in cl for x in ("/lb", "per pound", "per lb", " lb", "pound")):
        return "lb"
    if any(x in cl for x in ("/doz", "dozen", " dz", " doz")):
        return "doz"
    if "roll" in cl:
        return "ea"
    return "ea"


def _bare_price_allowed(text: str, price_pos: int) -> bool:
    clause = _clause_of(text, price_pos)
    clause_l = clause.lower()
    if _find_special_kw_in_clause(text, price_pos):
        return True
    if any(x in clause_l for x in ("roll", "each", "dinner", "special")):
        return True
    # Live lobster with size descriptor but no unit suffix
    if "lobster" in clause_l and _find_tier_left_of(text, price_pos):
        return True
    return False


def is_specials_post(text: str) -> bool:
    """AC4b: post mentions seafood special keywords AND contains $ price."""
    if not text or "$" not in text:
        return False
    text_l = text.lower()
    has_special_kw = any(kw in text_l for kw in SPECIALS_POST_KEYWORDS)
    if not has_special_kw:
        return False
    # Exclude lobster-only tier listing posts (no real specials content)
    lobster_only = (
        any(kw in text_l for kw in ("chicks", "hard shell", "soft shell", "old shell", "live lobster"))
        and not any(kw in text_l for kw in ("halibut", "scallops", "clams", "shrimp", "haddock", "salmon", "chowder"))
        and "roll" not in text_l
    )
    if lobster_only:
        return False
    return True


def _clause_contains(text: str, price_pos: int, kw: str) -> bool:
    clause = _clause_of(text, price_pos)
    return kw.lower() in clause.lower()


def parse_post(text: str) -> list[ParsedRow]:
    """Extract lobster tiers + oyster tiers + specials from FB post text."""
    if not text:
        return []
    rows: list[ParsedRow] = []

    for m in _PRICE_LB_RE.finditer(text):
        price = float(m.group(1))
        # Special keywords in clause take precedence over distant tier keywords
        if _clause_has_special_only(text, m.start()):
            continue
        tier = _find_tier_left_of(text, m.start())
        if tier:
            clause = _clause_of(text, m.start())
            clause_l = clause.lower()
            if any(kw in clause_l for kw in ("lobster meat", "picked meat", "bisque", "mac and cheese", "ravioli")):
                continue
            immediate = text[max(0, m.start() - 30):m.start()].lower()
            if "cooked" in immediate:
                continue
            if _clause_contains(text, m.start(), "oyster"):
                continue
            snippet = text[max(0, m.start() - 40):m.end() + 20].strip()[:120]
            rows.append(("lobster_tier", tier, price, "lb", snippet))

    text_lower = text.lower()
    has_oyster_mention = "oyster" in text_lower or "oysters" in text_lower
    for m in _PRICE_DOZ_RE.finditer(text):
        price = float(m.group(1))
        if not has_oyster_mention:
            continue
        clause = _clause_of(text, m.start())
        grade = _find_oyster_grade_in_clause(clause)
        if not grade:
            grade = "oyster"
        snippet = text[max(0, m.start() - 50):m.end() + 20].strip()[:120]
        rows.append(("oyster_tier", grade, price, "doz", snippet))

    tier_snippets = {r[4] for r in rows if r[0] == "lobster_tier"}
    for m in _PRICE_LB_RE.finditer(text):
        price = float(m.group(1))
        snippet = text[max(0, m.start() - 40):m.end() + 20].strip()[:120]
        if snippet in tier_snippets:
            continue
        kw = _find_special_kw_in_clause(text, m.start())
        if not kw:
            kw = _find_special_kw(text, m.start())
        if kw:
            clause = _clause_of(text, m.start())
            clause_l = clause.lower()
            if any(kw_x in clause_l for kw_x in ("lobster meat", "picked meat", "bisque", "mac and cheese", "ravioli")):
                continue
            key = _canonical_special_key(clause, kw)
            rows.append(("special", key, price, "lb", snippet))

    for m in _PRICE_EA_RE.finditer(text):
        price = float(m.group(1))
        kw = _find_special_kw_in_clause(text, m.start())
        if not kw:
            kw = _find_special_kw(text, m.start())
        if kw:
            clause = _clause_of(text, m.start())
            snippet = text[max(0, m.start() - 40):m.end() + 30].strip()[:120]
            key = _canonical_special_key(clause, kw)
            rows.append(("special", key, price, "ea", snippet))

    # Bare $ prices with contextual unit inference
    covered_positions = set()
    for pattern in (_PRICE_LB_RE, _PRICE_DOZ_RE, _PRICE_EA_RE):
        for m in pattern.finditer(text):
            covered_positions.add(m.start())

    for m in _PRICE_BARE_RE.finditer(text):
        if m.start() in covered_positions:
            continue
        if not _bare_price_allowed(text, m.start()):
            continue
        price = float(m.group(1))
        clause = _clause_of(text, m.start())
        clause_l = clause.lower()
        tier = _find_tier_left_of(text, m.start())
        if tier and "lobster" in clause_l and not _find_special_kw_in_clause(text, m.start()):
            if any(kw in clause_l for kw in ("lobster meat", "picked meat", "bisque")):
                continue
            immediate = text[max(0, m.start() - 30):m.start()].lower()
            if "cooked" in immediate:
                continue
            snippet = text[max(0, m.start() - 40):m.end() + 20].strip()[:120]
            rows.append(("lobster_tier", tier, price, "lb", snippet))
            continue
        kw = _find_special_kw_in_clause(text, m.start())
        if not kw:
            kw = _find_special_kw(text, m.start())
        if kw:
            if any(kw_x in clause_l for kw_x in ("lobster meat", "picked meat", "bisque", "mac and cheese", "ravioli")):
                continue
            unit = _infer_unit_from_clause(clause)
            snippet = text[max(0, m.start() - 40):m.end() + 20].strip()[:120]
            key = _canonical_special_key(clause, kw)
            rows.append(("special", key, price, unit, snippet))

    seen: set[tuple[str, str, float, str]] = set()
    deduped: list[ParsedRow] = []
    for r in rows:
        sig = (r[0], r[1], r[2], r[3])
        if sig not in seen:
            seen.add(sig)
            deduped.append(r)
    return deduped


def parse_post_with_meta(text: str) -> tuple[list[ParsedRow], list[ParseMeta]]:
    """Like parse_post but returns per-row metadata for quality gating."""
    rows = parse_post(text)
    meta: list[ParseMeta] = []
    for row in rows:
        kind, key, price, unit, snippet = row
        bare = "$" in snippet and not _has_explicit_unit_in_snippet(snippet, unit)
        meta.append({"price_pos": text.find(snippet[:20]) if snippet else 0, "bare_price": bare})
    return rows, meta


def _has_explicit_unit_in_snippet(snippet: str, unit: str) -> bool:
    s = snippet.lower()
    if unit == "lb":
        return any(x in s for x in ("/lb", "per pound", " lb", "a pound"))
    if unit == "doz":
        return any(x in s for x in ("/doz", "dozen", " dz", " doz"))
    if unit == "ea":
        return any(x in s for x in ("each", "/ea", "/roll", "per roll"))
    return False

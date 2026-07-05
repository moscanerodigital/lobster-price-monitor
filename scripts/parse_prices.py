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
# Each: (regex, canonical_tier)
_TIER_KEYWORDS: list[tuple[str, str]] = [
    (r"\b(?:chicks|chix)\b", "chicks"),
    (r"\b(?:soft\s*shell|softshell)\b", "soft_shell"),
    (r"\b(?:old\s*shell|oldshell)\b", "old_shell"),
    (r"\b(?:hard\s*shell|hardshell)\b", "hard_shell"),
    (r"\b(?:firm\s*shell|firm)\b", "hard_shell"),  # "Firm Shell" maps to hard_shell
    (r"\b(?:select|selects)\b", "select"),
    (r"(?:2\s*lb\s*(?:and|or|&)\s*(?:up|\+|plus)|2\s*lb\s*plus|2lb\+|2\s*pound\s*plus|\bjumbo)", "2lb_plus"),
    (r"(?:1\s*⅛|1\.125)\s*lb", "1.125lb"),
    (r"(?:1\s*¼|1\.25|1\s*1/4)\s*lb", "1.25lb"),
    (r"(?:1\s*½|1\.5|1\s*1/2)\s*lb", "1.5lb"),
    (r"(?:1\s*¾|1\.75|1\s*3/4)\s*lb", "1.75lb"),
]

# ---- Oyster size/grade keywords ----
# Order matters: more specific first. "single select" before "select", etc.
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

# ---- Price patterns ----
# $/lb style — handles $8.75/lb, $8.75 per pound, $8.75 a pound, $8.99lb, $8.75 lb
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
# $/dozen style — oysters: $24/doz, $24 dz, $24 a dozen, $24 dozen
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
# $/ea style — explicit units
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

# ---- Specials keywords (any seafood item, EXCLUDING lobster meat — that
#      is cooked/picked product, not live lobster. Erik wants live only.) ----
_SPECIAL_KEYWORDS = [
    "halibut", "scallops", "clams", "shrimp",
    "haddock", "salmon", "cod", "pollock", "tuna", "swordfish",
    "chowder", "bisque", "roll", "mac", "bake", "ravioli",
    "scallop", "clam", "crab",
    "smoked", "stew",
    # "lobster" and "meat" excluded — we want LIVE lobster only.
    # Lobster tier classification handles live lobster via the tier keywords.
    # "lobster meat" / "picked meat" / "lobster bisque" are excluded.
    # "oysters" is NOT in this list — oyster prices go through the dedicated
    # oyster_tier path (kind=oyster_tier, unit=doz, threshold alerts).
]

ParsedRow = tuple[Literal["lobster_tier", "oyster_tier", "special"], str, float, str, str]


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s[:80]


def _clause_of(text: str, pos: int) -> str:
    """Return the clause containing pos (text back to the most recent
    comma, semicolon, or '. '). Falls back to a 60-char window if no
    boundary is found."""
    start = max(
        text.rfind(",", 0, pos),
        text.rfind(";", 0, pos),
        text.rfind(". ", 0, pos),
    )
    if start >= 0:
        return text[start + 1:pos]
    return text[max(0, pos - 60):pos]


def _find_tier_left_of(text: str, price_pos: int) -> str | None:
    """Look left from price_pos for the nearest lobster tier keyword.

    Window strategy: a clause is delimited by `,` OR by `. ` (period+space)
    OR by `;`. Sentence boundaries matter because "1.25 lb" contains a `.`.

    Tier selection:
    1. Same clause as price: prefer non-size tier (chicks/old/hard/soft/select)
       over size tier when both appear — because in "Chicks 1 1/4 lbers $8.75"
       "Chicks" is the parent tier and "1 1/4" is just a size descriptor.
    2. If no tier in same clause: look in the IMMEDIATELY PRECEDING clause
       for size-tier only (handles "Hard shell $11.95, 2 lb and plus $12.75").
       Don't look further back — that risks leaking "1 1/4" from way back
       into a different clause's price."""
    size_tiers = {"1.125lb", "1.25lb", "1.5lb", "1.75lb", "2lb_plus"}
    window_start = max(0, price_pos - 160)
    left = text[window_start:price_pos]

    # Find ALL clause boundaries (positions of `,` `;` and `. ` (with space
    # and not in a number)).
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
    """Return the most specific oyster grade keyword in the clause, or None.

    Strategy: find all matches in the clause. If a non-named_variety grade
    (xl, select, standard, etc.) is present, prefer it over named_variety
    because the size/grade is the discriminating price tier. Within the
    same class (size or variety), take the leftmost match.
    """
    matches: list[tuple[int, str]] = []
    for pattern, canonical in _OYSTER_TIER_KEYWORDS:
        m = re.search(pattern, clause, re.IGNORECASE)
        if m:
            matches.append((m.start(), canonical))
    if not matches:
        return None
    # Prefer non-named_variety over named_variety
    grades = [c for _, c in matches if c != "named_variety"]
    if grades:
        # Take the leftmost non-variety match
        leftmost = min((m for m in matches if m[1] != "named_variety"), key=lambda x: x[0])
        return leftmost[1]
    # Only named_variety matches
    leftmost = min(matches, key=lambda x: x[0])
    return leftmost[1]


def _find_special_kw(text: str, around_pos: int) -> str | None:
    """Find any special keyword within ±80 chars of around_pos."""
    s = max(0, around_pos - 80)
    e = min(len(text), around_pos + 30)
    window = text[s:e].lower()
    for kw in _SPECIAL_KEYWORDS:
        if kw in window:
            return kw
    return None


def _clause_contains(text: str, price_pos: int, kw: str) -> bool:
    """Check if `kw` appears in the same clause as the price (case-insensitive).
    Falls back to a 60-char window if no clause boundary exists."""
    clause = _clause_of(text, price_pos)
    return kw.lower() in clause.lower()


def parse_post(text: str) -> list[ParsedRow]:
    """Extract lobster tiers + oyster tiers + specials from FB post text."""
    if not text:
        return []
    rows: list[ParsedRow] = []

    # 1. Lobster tier prices — for each $/lb price, find nearest tier LEFT of it
    for m in _PRICE_LB_RE.finditer(text):
        price = float(m.group(1))
        tier = _find_tier_left_of(text, m.start())
        if tier:
            # Exclude lobster meat / cooked / picked / bisque — those are not LIVE
            clause = _clause_of(text, m.start())
            clause_l = clause.lower()
            if any(kw in clause_l for kw in ("lobster meat", "picked meat", "bisque", "mac and cheese", "ravioli")):
                continue
            # "Cooked" only excludes if IMMEDIATELY before the price
            immediate = text[max(0, m.start() - 30):m.start()].lower()
            if "cooked" in immediate:
                continue
            # Also skip if this is actually an oyster (oyster takes precedence)
            if _clause_contains(text, m.start(), "oyster"):
                continue
            snippet = text[max(0, m.start() - 40):m.end() + 20].strip()[:120]
            rows.append(("lobster_tier", tier, price, "lb", snippet))

    # 2. Oyster tier prices — for each $/doz price, find oyster grade in clause
    text_lower = text.lower()
    has_oyster_mention = "oyster" in text_lower or "oysters" in text_lower
    for m in _PRICE_DOZ_RE.finditer(text):
        price = float(m.group(1))
        # Only treat as oyster if "oyster" appears ANYWHERE in the post —
        # FB posts often mention oysters once in the intro and then list
        # prices per variety in subsequent clauses.
        if not has_oyster_mention:
            continue
        clause = _clause_of(text, m.start())
        grade = _find_oyster_grade_in_clause(clause)
        if not grade:
            grade = "oyster"  # generic
        snippet = text[max(0, m.start() - 50):m.end() + 20].strip()[:120]
        rows.append(("oyster_tier", grade, price, "doz", snippet))

    # 3. Specials as $/lb (not already a lobster tier) — but only LIVE/non-lobster
    tier_snippets = {r[4] for r in rows if r[0] == "lobster_tier"}
    for m in _PRICE_LB_RE.finditer(text):
        price = float(m.group(1))
        snippet = text[max(0, m.start() - 40):m.end() + 20].strip()[:120]
        if snippet in tier_snippets:
            continue
        kw = _find_special_kw(text, m.start())
        if kw:
            clause = _clause_of(text, m.start())
            clause_l = clause.lower()
            if any(kw_x in clause_l for kw_x in ("lobster meat", "picked meat", "bisque", "mac and cheese", "ravioli")):
                continue
            rows.append(("special", _slug(snippet), price, "lb", snippet))

    # 4. $/ea specials (rolls, dinners) — explicit units
    for m in _PRICE_EA_RE.finditer(text):
        price = float(m.group(1))
        kw = _find_special_kw(text, m.start())
        if kw:
            snippet = text[max(0, m.start() - 40):m.end() + 30].strip()[:120]
            rows.append(("special", _slug(snippet), price, "ea", snippet))

    # Dedupe by (kind, key, price, unit)
    seen: set[tuple[str, str, float, str]] = set()
    deduped: list[ParsedRow] = []
    for r in rows:
        sig = (r[0], r[1], r[2], r[3])
        if sig not in seen:
            seen.add(sig)
            deduped.append(r)
    return deduped

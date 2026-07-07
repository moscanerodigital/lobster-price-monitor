"""Self-hosted Caveat font CSS (no Google Fonts request)."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

_WEIGHT_FILES: tuple[tuple[str, str], ...] = (
    ("Caveat-Variable.ttf", "truetype"),
    ("Caveat-Medium.woff2", "woff2"),
    ("Caveat-Medium.ttf", "truetype"),
)


def _font_data_uri(path: Path, fmt: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    mime = "font/woff2" if fmt == "woff2" else "font/truetype"
    return f"data:{mime};base64,{encoded}"


@lru_cache(maxsize=1)
def caveat_font_face_css() -> str:
    """Return @font-face rules with data: URIs, or system fallback if files missing."""
    variable = FONTS_DIR / "Caveat-Variable.ttf"
    if variable.is_file():
        data_uri = _font_data_uri(variable, "truetype")
        return (
            "@font-face {\n"
            "  font-family: 'Caveat';\n"
            "  font-style: normal;\n"
            "  font-weight: 500 700;\n"
            "  font-display: swap;\n"
            f"  src: url({data_uri}) format('truetype');\n"
            "}"
        )

    for name, fmt in _WEIGHT_FILES[1:]:
        path = FONTS_DIR / name
        if path.is_file():
            data_uri = _font_data_uri(path, fmt)
            return (
                "@font-face {\n"
                "  font-family: 'Caveat';\n"
                "  font-style: normal;\n"
                "  font-weight: 500;\n"
                "  font-display: swap;\n"
                f"  src: url({data_uri}) format('{fmt}');\n"
                "}"
            )

    return (
        "/* Caveat not vendored — using system cursive fallback */\n"
        "body { font-family: 'Segoe Print', 'Bradley Hand', cursive; }"
    )

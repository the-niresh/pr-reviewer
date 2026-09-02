"""Deliberate reviewer TUI colour theme.

Warm near-black and amber, chosen on purpose to read as this product's own terminal rather
than the stock Tailwind sky/slate default. Severity colours for findings live in
SEVERITY_COLORS, kept separate from the brand accent (also amber) so a "critical" finding
can never be mistaken for "this is just our colour scheme".
"""

from __future__ import annotations

from types import MappingProxyType

from textual.theme import Theme

REVIEWER_THEME = Theme(
    name="reviewer",
    primary="#e8a33d",
    secondary="#c98a5b",
    accent="#e8a33d",
    warning="#f76808",
    error="#e5484d",
    success="#46a758",
    background="#0b0b0d",
    surface="#16151a",
    panel="#232128",
    foreground="#e8e3d9",
    dark=True,
)

SEVERITY_COLORS: MappingProxyType[str, str] = MappingProxyType(
    {
        "critical": "#e5484d",
        "high": "#f76808",
        "medium": "#e8a33d",
        "low": "#8b8578",
    }
)

REVIEWER_CSS = """
Screen {
    background: $background;
}

#main-layout {
    height: 100%;
}

#section-content {
    background: $surface;
    color: $foreground;
    padding: 1 2;
    width: 1fr;
    border-left: heavy transparent;
}

#section-content:focus-within {
    border-left: heavy $accent;
}
"""

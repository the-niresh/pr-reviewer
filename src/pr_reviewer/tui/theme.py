"""Deliberate reviewer TUI colour theme."""

from __future__ import annotations

from textual.theme import Theme

REVIEWER_THEME = Theme(
    name="reviewer",
    primary="#38bdf8",
    secondary="#818cf8",
    accent="#f472b6",
    warning="#fbbf24",
    error="#f87171",
    success="#4ade80",
    background="#0f172a",
    surface="#1e293b",
    panel="#334155",
    foreground="#e2e8f0",
    dark=True,
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
}
"""

"""Helpers for quoting repository-specific user prompts."""

from __future__ import annotations

from pr_reviewer.security.prompt_boundaries import UntrustedText, wrap_untrusted


def quote_repository_prompt(content: str) -> str:
    return wrap_untrusted("repository_prompt", UntrustedText(content))

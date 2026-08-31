"""In-process immutable prompt versions. No database handle: runner and hosted both import this."""

from __future__ import annotations

from dataclasses import dataclass


class PromptVersionImmutable(Exception):
    """An existing name and version cannot be rewritten."""


class PromptNotFound(Exception):
    """No prompt is registered under that name and version."""


@dataclass(frozen=True)
class PromptVersion:
    name: str
    version: str
    content: str


class PromptRegistry:
    def __init__(self) -> None:
        self._versions: dict[tuple[str, str], PromptVersion] = {}

    def register(self, name: str, version: str, content: str) -> PromptVersion:
        key = (name, version)
        if key in self._versions:
            raise PromptVersionImmutable()
        item = PromptVersion(name=name, version=version, content=content)
        self._versions[key] = item
        return item

    def get(self, name: str, version: str) -> PromptVersion:
        try:
            return self._versions[(name, version)]
        except KeyError as exc:
            raise PromptNotFound() from exc

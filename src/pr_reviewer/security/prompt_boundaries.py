"""The single approved way to place repository text in a prompt."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

UNTRUSTED_BEGIN = "-----BEGIN UNTRUSTED INPUT-----"
UNTRUSTED_END = "-----END UNTRUSTED INPUT-----"


@dataclass(frozen=True)
class UntrustedText:
    """Repository text that cannot be interpolated. wrap_untrusted is the only string exit."""

    _raw: str = field(repr=False)

    def __str__(self) -> str:
        raise TypeError("untrusted text cannot be converted to str; use wrap_untrusted")

    def __format__(self, format_spec: str) -> str:
        raise TypeError("untrusted text cannot be interpolated; use wrap_untrusted")


def _strip_markers(text: str) -> str:
    while UNTRUSTED_BEGIN in text or UNTRUSTED_END in text:
        previous_length = len(text)
        text = text.replace(UNTRUSTED_BEGIN, "").replace(UNTRUSTED_END, "")
        if len(text) >= previous_length:
            raise RuntimeError("untrusted marker strip did not shrink")
    return text


def wrap_untrusted(label: str, content: UntrustedText) -> str:
    if not isinstance(content, UntrustedText):
        raise TypeError("wrap_untrusted requires UntrustedText")
    safe_label = _strip_markers(label)
    safe_content = _strip_markers(content._raw)
    wrapped = f"{UNTRUSTED_BEGIN}\nname: {safe_label}\n{safe_content}\n{UNTRUSTED_END}"
    if wrapped.count(UNTRUSTED_BEGIN) != 1 or wrapped.count(UNTRUSTED_END) != 1:
        raise RuntimeError("wrap_untrusted must emit exactly one BEGIN and one END")
    return wrapped


def wrap_untrusted_review_inputs(
    *,
    diff: UntrustedText,
    title: UntrustedText,
    body: UntrustedText,
    commit_messages: Sequence[UntrustedText],
    review_comments: Sequence[UntrustedText],
    retrieved_chunks: Sequence[UntrustedText],
) -> list[str]:
    sections = [
        wrap_untrusted("diff", diff),
        wrap_untrusted("pr_title", title),
        wrap_untrusted("pr_body", body),
    ]
    for message in commit_messages:
        sections.append(wrap_untrusted("commit_message", message))
    for comment in review_comments:
        sections.append(wrap_untrusted("review_comment", comment))
    for chunk in retrieved_chunks:
        sections.append(wrap_untrusted("retrieved_chunk", chunk))
    return sections

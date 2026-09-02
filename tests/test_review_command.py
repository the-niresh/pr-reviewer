"""`reviewer review <owner/repo#pr>` (runner/cli/review.py).

Exercises the command's own contract, not the live GitHub/model wiring: LiveAgentReviewBackend is
monkeypatched out for a fake so these tests never touch the network. What matters here is that the
command parses owner/repo#pr, picks the documented exit code for each outcome, and that --json
puts exactly one JSON document on stdout with all human-readable text on stderr instead.
"""

from __future__ import annotations

import json
from io import StringIO

import pytest

import pr_reviewer.runner.cli.review as review_module
from pr_reviewer.agent_surfaces.core import (
    AgentReviewRequest,
    AgentSurfaceRefusal,
    GitHubConnectionState,
    RemediationPrompt,
    SurfaceFinding,
    SurfaceReview,
    remediation_prompt_for_finding,
)


def _finding() -> SurfaceFinding:
    return SurfaceFinding(
        id="finding-1",
        concern="correctness",
        severity="high",
        category="null-check",
        file_path="app.py",
        line_start=12,
        line_end=12,
        title="Missing null check",
        rationale="value can be None before it is used.",
        evidence=("app.py:12",),
        confidence=0.82,
    )


class FakeBackend:
    def __init__(
        self,
        *,
        connected: bool = True,
        findings: tuple[SurfaceFinding, ...] = (),
        raise_error: Exception | None = None,
    ) -> None:
        self.connected = connected
        self.findings = findings
        self.raise_error = raise_error
        self.requests: list[AgentReviewRequest] = []

    def github_connection_state(self) -> GitHubConnectionState:
        return GitHubConnectionState(
            connected=self.connected,
            reason=None if self.connected else "GitHub is not connected.",
        )

    def start_review(self, request: AgentReviewRequest) -> SurfaceReview:
        self.requests.append(request)
        if self.raise_error is not None:
            raise self.raise_error
        return SurfaceReview(
            review_id="review-1",
            owner=request.owner,
            repository=request.repository,
            pull_request=request.pull_request,
            head_sha="deadbeef00000000000000000000000000000000",
            status="complete",
            findings=self.findings,
            remediation_prompts=tuple(
                remediation_prompt_for_finding(f) for f in self.findings
            ),
        )

    def list_findings(self, review_id: str) -> tuple[SurfaceFinding, ...]:
        raise NotImplementedError

    def list_remediation_prompts(self, review_id: str) -> tuple[RemediationPrompt, ...]:
        raise NotImplementedError


def _patch_backend(monkeypatch: pytest.MonkeyPatch, backend: FakeBackend) -> None:
    monkeypatch.setattr(review_module, "LiveAgentReviewBackend", lambda: backend)


def _run(argv: list[str]) -> tuple[int, str, str]:
    stdout, stderr = StringIO(), StringIO()
    code = review_module.main(argv, stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def test_review_with_no_findings_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_backend(monkeypatch, FakeBackend(findings=()))

    code, out, err = _run(["acme/widgets#12"])

    assert code == review_module.EXIT_OK_NO_FINDINGS
    assert "No findings" in out
    assert err == ""


def test_review_with_findings_exits_one(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_backend(monkeypatch, FakeBackend(findings=(_finding(),)))

    code, out, err = _run(["acme/widgets#12"])

    assert code == review_module.EXIT_OK_FINDINGS
    assert "Missing null check" in out
    assert "asserted" in out
    assert err == ""


def test_review_refused_exits_two(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_backend(monkeypatch, FakeBackend(connected=False))

    code, out, err = _run(["acme/widgets#12"])

    assert code == review_module.EXIT_REFUSED
    assert out == ""
    assert "GitHub is not connected" in err


def test_review_unexpected_failure_exits_three(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_backend(monkeypatch, FakeBackend(raise_error=RuntimeError("boom")))

    code, out, err = _run(["acme/widgets#12"])

    assert code == review_module.EXIT_ERROR
    assert out == ""
    assert "Review failed unexpectedly" in err
    assert "boom" not in err


def test_bad_pull_request_ref_exits_three(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_backend(monkeypatch, FakeBackend())

    code, out, err = _run(["not-a-valid-ref"])

    assert code == review_module.EXIT_ERROR
    assert out == ""
    assert "owner/repo#pr" in err


def test_json_mode_prints_exactly_one_json_document_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_backend(monkeypatch, FakeBackend(findings=(_finding(),)))

    code, out, err = _run(["acme/widgets#12", "--json"])

    assert code == review_module.EXIT_OK_FINDINGS
    assert err == ""
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected exactly one line on stdout, got: {out!r}"
    payload = json.loads(lines[0])
    assert payload["status"] == "ok"
    result = payload["result"]
    assert result["review_id"] == "review-1"
    assert result["owner"] == "acme"
    assert result["repository"] == "widgets"
    assert result["pull_request"] == 12
    assert result["head_sha"]
    assert result["status"] == "complete"
    finding = result["findings"][0]
    for key in (
        "severity",
        "concern",
        "file_path",
        "line_start",
        "line_end",
        "title",
        "rationale",
        "verified",
    ):
        assert key in finding


def test_json_mode_refusal_is_one_json_document_on_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_backend(monkeypatch, FakeBackend(connected=False))

    code, out, err = _run(["acme/widgets#12", "--json"])

    assert code == review_module.EXIT_REFUSED
    assert err == ""
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["status"] == "refused"
    assert payload["refusal"]["code"] == "github_not_connected"


def test_json_mode_error_is_one_json_document_on_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_backend(monkeypatch, FakeBackend(raise_error=RuntimeError("boom")))

    code, out, err = _run(["acme/widgets#12", "--json"])

    assert code == review_module.EXIT_ERROR
    assert err == ""
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["status"] == "error"
    assert payload["error"] == {
        "code": "unexpected_error",
        "message": "Review failed unexpectedly.",
        "action": "Check the local logs, fix the cause, then retry the request.",
    }
    assert "Traceback" not in out
    assert "boom" not in out


def test_json_mode_out_of_tokens_is_structured_without_provider_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_backend(
        monkeypatch,
        FakeBackend(
            raise_error=AgentSurfaceRefusal(
                "out_of_tokens",
                (
                    "OpenAI balance is exhausted. "
                    "Add credits or switch provider to continue reviewing."
                ),
                action="Add credits or switch provider, then retry the review.",
            )
        ),
    )

    code, out, err = _run(["acme/widgets#12", "--json"])

    assert code == review_module.EXIT_REFUSED
    assert err == ""
    payload = json.loads(out)
    assert payload["status"] == "refused"
    assert payload["refusal"] == {
        "code": "out_of_tokens",
        "message": (
            "OpenAI balance is exhausted. "
            "Add credits or switch provider to continue reviewing."
        ),
        "action": "Add credits or switch provider, then retry the review.",
    }
    assert "raw provider" not in out


def test_help_documents_exit_codes() -> None:
    with pytest.raises(SystemExit) as excinfo:
        review_module.main(["--help"], stdout=StringIO(), stderr=StringIO())
    assert excinfo.value.code == 0

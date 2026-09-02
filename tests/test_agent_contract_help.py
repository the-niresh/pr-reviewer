from __future__ import annotations

from io import StringIO

from pr_reviewer.reviewer_entry import main as reviewer_main
from pr_reviewer.runner.cli import a2a, acp, mcp, review


def test_reviewer_help_lists_agent_commands_outputs_and_exit_codes(
    capsys: object,
) -> None:
    exit_code = reviewer_main(["--help"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "reviewer review owner/repo#pr --json" in captured.out
    assert "reviewer mcp" in captured.out
    assert "JSON result statuses: ok, refused, error" in captured.out
    assert "exit codes:" in captured.out
    assert "1  review completed, findings present" in captured.out


def test_review_help_documents_json_shape_and_failure_exit_code() -> None:
    stdout = StringIO()

    try:
        review.main(["--help"], stdout=stdout, stderr=StringIO())
    except SystemExit as exc:
        assert exc.code == 0

    output = stdout.getvalue()
    assert '"status": "ok"' in output
    assert '"refusal": {"code": "...", "message": "...", "action": "..."}' in output
    assert '"error": {"code": "...", "message": "...", "action": "..."}' in output
    assert "3  failure" in output


def test_agent_stdio_help_documents_protocol_shape_and_exit_codes() -> None:
    for module, command, method in (
        (mcp, "reviewer mcp", "tools/call"),
        (a2a, "reviewer a2a", "message/send"),
        (acp, "reviewer acp", "actions/call"),
    ):
        stdout = StringIO()

        try:
            module.main(["--help"], stdin=StringIO(""), stdout=stdout)
        except SystemExit as exc:
            assert exc.code == 0

        output = stdout.getvalue()
        assert command in output
        assert method in output
        assert "status: ok, refused, error" in output
        assert "error: {code, message, action}" in output
        assert "exit codes:" in output
        assert "0  stdio loop ended or help was printed" in output

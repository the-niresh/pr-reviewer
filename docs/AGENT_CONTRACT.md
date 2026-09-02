# Agent-Facing Contract

This document describes how another agent should drive `reviewer` without reading the source.

## Commands

`reviewer --help` lists all commands. Each subcommand also accepts `--help`.

The agent-facing review surfaces are:

- `reviewer review owner/repo#pr --json`
- `reviewer mcp`
- `reviewer a2a`
- `reviewer acp`

The terminal UI starts with `reviewer` when stdin is a terminal. It is for humans, not for agent automation.

## Exit Codes

`reviewer review` uses distinct exit codes:

- `0` - review completed and found no findings.
- `1` - review completed and found one or more findings.
- `2` - request was refused before a review could complete.
- `3` - request failed.

The stdio server commands use:

- `0` - help was printed or stdin closed cleanly.

Protocol-level errors are returned as JSON-RPC or ACP error payloads. They do not change the process exit code while the stdio loop is alive.

## JSON Result Shape

Every agent result payload has one of three statuses.

Success:

```json
{
  "status": "ok",
  "result": {}
}
```

Refusal:

```json
{
  "status": "refused",
  "refusal": {
    "code": "github_not_connected",
    "message": "GitHub is not connected. Connect GitHub before requesting a review.",
    "action": "Connect GitHub, then retry the request."
  }
}
```

Failure:

```json
{
  "status": "error",
  "error": {
    "code": "unexpected_error",
    "message": "Review failed unexpectedly.",
    "action": "Check the local logs, fix the cause, then retry the request."
  }
}
```

Do not parse human text. Use `status`, `refusal.code`, `error.code`, and the process exit code.

## Review Result Shape

A review result has this shape:

```json
{
  "review_id": "review-1",
  "owner": "acme",
  "repository": "widgets",
  "pull_request": 12,
  "head_sha": "deadbeef00000000000000000000000000000000",
  "status": "complete",
  "findings": [
    {
      "id": "finding-1",
      "concern": "correctness",
      "severity": "high",
      "category": "null-check",
      "file_path": "app.py",
      "line_start": 12,
      "line_end": 12,
      "title": "Missing null check",
      "rationale": "value can be None before it is used.",
      "evidence": ["app.py:12"],
      "confidence": 0.82,
      "verified": false
    }
  ],
  "remediation_prompts": [
    {
      "finding_id": "finding-1",
      "prompt": "Fix this PR review finding..."
    }
  ]
}
```

`status` can be `queued`, `running`, `complete`, `cancelled`, or `failed`.

## Error Codes

Current stable codes:

- `github_not_connected` - connect GitHub, then retry.
- `no_model_key` - set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`, then retry.
- `out_of_tokens` - add credits or switch provider, then retry.
- `unknown_review` - run a review first, then use its `review_id`.
- `invalid_request` - fix command arguments or JSON-RPC arguments.
- `model_key_invalid` - set a valid provider key.
- `provider_rate_limited` - wait for the provider limit to reset.
- `context_limit_exceeded` - use a model with a larger context window or review a smaller pull request.
- `model_timeout` - retry after checking provider status.
- `invalid_model_response` - retry, or switch provider or model if it repeats.
- `provider_failure` - check provider status and local provider settings.
- `unexpected_error` - check local logs, fix the cause, then retry.

The `out_of_tokens` payload never includes the raw provider reason. That reason can contain provider JSON.

## Worked Examples

CLI JSON:

```bash
reviewer review acme/widgets#12 --json
```

```json
{"status":"ok","result":{"review_id":"review-1","owner":"acme","repository":"widgets","pull_request":12,"head_sha":"deadbeef00000000000000000000000000000000","status":"complete","findings":[],"remediation_prompts":[]}}
```

MCP:

```json
{"jsonrpc":"2.0","id":"tools-1","method":"tools/list","params":{}}
```

```json
{"jsonrpc":"2.0","id":"call-1","method":"tools/call","params":{"name":"review_pull_request","arguments":{"owner":"acme","repository":"widgets","pull_request":12}}}
```

A2A:

```json
{"jsonrpc":"2.0","id":"call-1","method":"message/send","params":{"message":{"role":"user","messageId":"message-1","parts":[{"kind":"data","data":{"command":"review_pull_request","arguments":{"owner":"acme","repository":"widgets","pull_request":12}}}]}}}
```

ACP:

```json
{"id":"init-1","method":"initialize","params":{}}
```

```json
{"id":"call-1","method":"actions/call","params":{"name":"review_pull_request","arguments":{"owner":"acme","repository":"widgets","pull_request":12}}}
```

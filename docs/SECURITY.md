# Security

| Mark | Means |
|---|---|
| ⬜ | Not done yet |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision |
| ⚠️ | Known trap |

Each control names the test that proves it. This document has no quality or
cost-per-PR numbers.

## 1 - ✅ Three authorization axes

Hosted authorization is installation, then repository, then runner.

1. **Installation.** Identity is the numeric GitHub installation id, not the
   display name (`tests/test_control_plane_identity.py::test_repository_identity_is_the_numeric_github_id_not_the_name`).
   Cross-installation access is denied
   (`test_cross_installation_access_is_denied_for_a_repository_registered_elsewhere`).
   A lookup filtered only by repository id is a cross-tenant read. Unscoped
   queries are forbidden (`tests/test_retention.py::test_retention_does_not_use_a_where_clause_on_installation_alone`).
2. **Repository.** Pairing approval is denied for a repository outside the
   verified set (`tests/test_pairing_approval_api.py::test_approval_denied_for_a_repository_outside_the_verified_set`).
   A runner assigned to a different repository cannot reach this one
   (`test_runner_assigned_to_a_different_repository_cannot_reach_this_one`).
   The token broker re-checks lease, repository, and head SHA before minting
   (`tests/test_token_broker.py::test_issued_token_is_scoped_to_the_job_repository_and_minimal_read_permissions`).
3. **Runner.** Wrong runner scope on the dashboard is indistinguishable from
   not found (`tests/test_dashboard_auth.py::test_wrong_runner_scope_is_indistinguishable_from_not_found`).
   A revoked runner fails authorization
   (`test_revoked_runner_fails_authorization`). Account data uses the paired
   runner identity, not the local session cookie
   (`test_account_uses_paired_runner_identity_not_the_local_session`).

A GitHub HMAC proves GitHub sent the body. It does not replace these three
axes (`tests/test_webhook.py::test_webhook_rejects_invalid_signature`).

## 2 - ✅ Token and PEM redaction

Connector audit persists `ConnectorAudit` only. Token-shaped strings and PEM
headers are redacted (`tests/test_connector_contracts.py`). Issued installation
tokens are never persisted in Neon
(`tests/test_token_broker.py::test_issued_token_is_never_persisted_in_neon`).
Runner credentials are stored only as hashes
(`test_runner_credential_is_stored_only_as_a_hash`). Trace JSON export strips
secret-like keys (`tests/test_trace_cli.py::test_cli_json_export_redacts_secret_like_keys_and_shapes_segments`).

## 3 - ✅ Untrusted-text prompt boundary

Repository text reaches a prompt only through `wrap_untrusted`
(`security/prompt_boundaries.py:34`). `UntrustedText` cannot be interpolated
or concatenated (`tests/test_prompt_boundaries.py::test_untrusted_text_cannot_be_interpolated_or_concatenated`).
Inner delimiter breakouts are stripped
(`test_wrap_untrusted_strips_inner_delimiter_breakout`).

## 4 - ✅ Loopback dashboard, deny by default, CSRF

`create_dashboard_app` binds loopback, disables docs, Redoc, and OpenAPI
(`web/dashboard_api.py:67`). The guard is deny by default:
`if not public and not session_is_valid(...)` (`web/dashboard_api.py:98`).
Unauthenticated `/openapi.json` and unknown paths are not 200
(`tests/test_dashboard_auth.py::test_unauthenticated_docs_and_unknown_paths_are_not_ok`).
Non-loopback clients get 403 (`test_non_loopback_client_is_denied`). Writes
without CSRF are denied (`test_write_without_csrf_is_denied`). Cookie flags
are strict (`test_session_cookie_flags_are_strict`). There is no webhook
route on the dashboard (`test_dashboard_exposes_no_webhook_route`).

## 5 - ✅ Docker sandbox

Untrusted commands run only inside Docker. Missing Docker never executes the
spec command on the host
(`tests/test_doctor_docker.py::test_run_never_executes_spec_command_on_the_host_when_docker_is_missing`).
Commands are argv, never a shell string
(`test_run_passes_command_as_argv_never_as_a_shell_string`). Doctor never
offers to install Docker (`test_doctor_never_offers_to_install_docker`).

## 6 - ✅ Retention and deletion

`uninstall_repository` deletes one repository. A sibling and the installation
stay (`tests/test_retention.py::test_uninstall_one_repository_leaves_sibling_and_installation_intact`).
Uninstall of the runner preserves local reviews unless `--confirm-delete`
(`tests/test_runner_uninstall.py`). A late sweep raises rather than hanging
(`test_retention_sweep_raises_loudly_when_the_deadline_passes`).

## 7 - ✅ Installer checksum

`scripts/install.sh` runs `sha256sum -c` before copying
(`tests/test_installer.py::test_install_script_verifies_checksum_and_rejects_bad_digest`).
There are no secret flags (`test_install_script_has_no_secret_flags`). Setup
rejects secret-bearing argv (`test_setup_rejects_secret_bearing_flags`).
Update refuses a checksum mismatch
(`tests/test_runner_update.py::test_update_refuses_to_replace_a_file_when_the_checksum_does_not_match`).

## 8 - ✅ Secret scan of the tracked tree

Command, run 2026-09-01 against this checkout:

```text
$ git grep -nEi 'BEGIN [A-Z ]*PRIVATE KEY|github_pat_|gh[pousr]_[A-Za-z0-9_]{20,}|postgres(ql)?://[^@[:space:]]+:[^@[:space:]]+@|sk-[A-Za-z0-9]{20,}' -- ':!*.md' ':!.env.example'
```

Result: the scan printed matches. Every hit was one of:

- the local compose URL `postgresql://pr_reviewer:pr_reviewer@localhost:54329` in
  `src/pr_reviewer/config.py` and tests
- password interpolation for loopback pgvector in `local_store/postgres.py`
- redaction regexes in `connectors/audit.py`
- test canaries (`gho_must_never_be_stored`, `-----BEGIN PRIVATE KEY-----` fixtures)

No live Neon URL, no GitHub PAT, and no PEM file is tracked. `.env` is gitignored.

## Settled - ✅

- ✅ Installation, repository, and runner are distinct axes.
- ✅ Untrusted repository text cannot skip `wrap_untrusted`.
- ✅ Dashboard deny-by-default is tested, including `/openapi.json`.

## Open Decisions - ❓

- ❓ When the leaked historical Neon URL is rotated. That credential is not
  in this tree. Rotation is a human action.

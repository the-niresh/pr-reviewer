# Data boundaries

This is the human-readable half of the hosted/local data boundary. The enforced half is
`src/pr_reviewer/control_plane/boundary.py`: `assert_no_private_columns` reads the live hosted
schema and fails loudly if a column could hold private review data. Run
`python3 scripts/generate_data_boundaries_doc.py` after changing `boundary.ALLOWLIST` so the two
cannot drift; `--check` exits 1 if this file is stale.

Background: `docs/phases/phase-2-security-design-gate.md`, section 4 ("Assume breach"). If the
control plane is fully compromised, the attacker gets identity records, repository IDs, job
state, redacted lifecycle events, aggregate token/cost numbers, and runner credential **hashes**.
They must never get source, diffs, findings, rationale, sandbox logs, embeddings, or a model key.
Those must never exist on that machine.

## Hosted (control plane, Neon)

Every column on every hosted table is one of two things: an auto-permitted scalar type that
cannot hold free text, or an allowlisted column with a documented reason. Anything else fails
`assert_no_private_columns`. `HOSTED_EXEMPTIONS` (a third, table-level escape hatch) is empty and
must stay that way -- see Exemptions below.

<!-- BEGIN GENERATED HOSTED ALLOWLIST -->
| Table | Column | Reason |
|---|---|---|
| `agent_events` | `event_type` | Lifecycle event name from a fixed, code-controlled set (e.g. review_job_failed, model_call.recorded), never derived from repository or review content. |
| `agent_events` | `payload` | Redacted lifecycle event detail only: identifiers, enums, and aggregate token/cost numbers. agent_events_payload_is_flat (migration 202608291930_rescope_hosted_events.sql) rejects a nested object or array at the database layer, and record_event.serialize_json_object rejects one at the application layer, so this column cannot hold a findings list, a diff, or a sandbox log. |
| `agent_reasoning` | `concern` | Fixed enum, the same closed set as review_findings.concern, enforced by a check constraint. |
| `agent_reasoning` | `reasoning` | Per-agent reasoning text, explicitly allowed by requirements.md's 'What reaches the server' list. No writer exists yet -- Phase 26's local persistence and review_projection.py land after this migration -- so this entry states the column type is allowed, not that a real writer has been proved safe yet. |
| `connector_circuits` | `connector` | Connector name from a fixed set (e.g. github), an operational identifier, not review content. |
| `connector_circuits` | `last_error_kind` | Closed-set error class name for the last failure that opened the circuit, never a stack trace or response body. |
| `connector_circuits` | `state` | Fixed enum ('closed', 'open', 'half_open'), the circuit breaker state. Unknown reads are treated as open in application code. |
| `connector_runs` | `connector` | Fixed enum ('github'), the outbound API this row audited, not review content. |
| `connector_runs` | `external_id` | Opaque GitHub request identifier when one is present. Typed and redacted so it cannot hold a token, a header, or a payload. |
| `connector_runs` | `operation` | Fixed enum ('create_installation_token', 'fetch_pull_request', 'create_pull_request_review'), the named call that ran, not a request or response body. |
| `connector_runs` | `payload_hash` | sha256 hex of operation, status, and byte counts only. The payload itself is never stored; this hash cannot be reversed into a body, a token, or a patch. |
| `github_deliveries` | `event_name` | GitHub webhook event name, a fixed enum (e.g. pull_request). |
| `github_deliveries` | `id` | GitHub's own delivery id: an opaque identifier, not content. |
| `installations` | `account_login` | GitHub account or org login: a public identifier GitHub itself shows on every page of the installation, not review content. |
| `model_calls` | `model_name` | Model name from our own configured model list (e.g. gpt-5-mini), an identifier, not review content. |
| `model_calls` | `provider` | Fixed enum ('openai', 'anthropic'), an identifier for which model API served the call, not review content. |
| `notification_channels` | `confidentiality` | Fixed enum ('restricted', 'ordinary') declared by the operator. Default is restricted. Never inferred from the transport, never a finding title. |
| `notification_channels` | `endpoint_hash` | A one-way hash of the webhook URL. The URL itself is never stored, so this column cannot be reversed back into it. |
| `notification_channels` | `name` | Operator-chosen label for a notification destination, not review content. |
| `notification_channels` | `purpose` | Fixed enum ('security_alert', 'review_ping'), which job this channel may carry, not review content. |
| `notification_channels` | `transport` | Fixed enum ('slack', 'telegram', 'discord'), the outbound transport, not a webhook URL and not review content. |
| `oauth_states` | `binding_hash` | A one-way hash of the per-attempt binding secret. The secret itself is never stored, so this column cannot be reversed back into it. |
| `oauth_states` | `return_to` | One of our own fixed, allowlisted control-plane paths (see github_oauth.ALLOWED_RETURN_TO_PATHS), validated before this row is ever written. Never a caller-supplied URL, never review content. |
| `oauth_states` | `state_hash` | A one-way hash of the OAuth state value. The state itself is never stored, so this column cannot be reversed back into it. |
| `pairing_codes` | `challenge` | PKCE code_challenge sent by the runner before any human is involved. Not secret, and not reversible to the verifier it was derived from; not review content either way. |
| `pairing_codes` | `code_hash` | A one-way hash of the pairing code. The code itself is never stored, so this column cannot be reversed back into it. |
| `pairing_codes` | `device_name` | Operator-chosen label for the runner device being paired, not review content. |
| `pairing_codes` | `repository_ids` | Our own repositories.id values selected at approval, an array of opaque identifiers, not repository content. |
| `prompt_versions` | `content` | Our own prompt template text, operational config we author ourselves, not a customer's source, diff, or finding. Insert-only: record_prompt_version writes a new name and version, and the prompt_versions_immutable_update trigger rejects any UPDATE. |
| `prompt_versions` | `name` | Name of one of our own prompt templates, not customer content. |
| `prompt_versions` | `version` | Version label for one of our own prompt templates. |
| `repositories` | `name` | GitHub repository name: an identifier, not repository content. |
| `repository_budget_reservations` | `status` | Fixed enum ('held', 'released', 'committed'), whether one job still holds a slice of the repository budget. Not review content. |
| `review_findings` | `category` | A short finding category label (e.g. 'null-check'), not the finding's source or diff. |
| `review_findings` | `concern` | Fixed enum ('security', 'correctness', 'tests', 'docs', 'maintainability'), enforced by a check constraint, not free text. |
| `review_findings` | `file_path` | Path of the file the finding is about: an identifier GitHub itself already shows on the PR, not file content. |
| `review_findings` | `id` | Our own finding id (contracts/finding.py), an opaque identifier. |
| `review_findings` | `rationale` | Findings text (the reasoning behind a finding), explicitly allowed by the same list as title. Never a diff hunk, source, or a sandbox log; those stay local. |
| `review_findings` | `severity` | Fixed enum ('critical', 'high', 'medium', 'low', 'info'), enforced by a check constraint. |
| `review_findings` | `status` | Fixed enum ('draft', 'queued_for_human', 'posted', 'rejected', 'disputed'), enforced by a check constraint. |
| `review_findings` | `title` | Findings text. requirements.md's 'What reaches the server' list explicitly names findings text as allowed; this is the model-authored summary line from contracts/finding.py, never a diff hunk or raw source. |
| `review_findings` | `verification_method` | Fixed enum ('sandbox', 'static', 'not_applicable', 'failed'), enforced by a check constraint, not review content. |
| `review_jobs` | `base_sha` | GitHub base commit SHA: an identifier, not repository content. |
| `review_jobs` | `delivery_id` | References github_deliveries.id, an opaque identifier. |
| `review_jobs` | `head_sha` | GitHub head commit SHA: an identifier, not repository content. |
| `review_jobs` | `last_error` | One of ReviewJobErrorClass's fixed values (contracts/errors.py), never a caller-supplied string: fail_review_job rejects anything else before it reaches this column, so it can never hold a diff, a stack trace, or file content. |
| `review_jobs` | `lease_token_hash` | A one-way hash of the job lease token. The token itself is never stored, so this column cannot be reversed back into it. |
| `review_jobs` | `locked_by` | Worker id holding the current lease, an operational identifier. |
| `review_jobs` | `policy_version` | Our own policy version label applied to the job, operational config, not review content. |
| `review_jobs` | `status` | Fixed enum ('pending', 'running', 'succeeded', 'failed', 'superseded', 'cancelled'), enforced by a check constraint. |
| `runners` | `credential_hash` | A one-way hash of the runner's credential. The credential itself is never stored, so this column cannot be reversed back into it. |
| `runners` | `device_name` | Operator-chosen label for a runner device, not review content. |
| `runners` | `mode` | Fixed enum ('analysis_only', 'full'), enforced by a check constraint. |
| `runners` | `platform` | Runner platform identifier (e.g. darwin-arm64), not review content. |
| `runners` | `version` | Runner software version string. |
| `schema_migrations` | `checksum` | sha256 hex digest of a migration file, an opaque hash. |
| `schema_migrations` | `filename` | Our own migration filename: code structure metadata, not review content. |

Every other hosted column is either `uuid`, `timestamptz`, `integer`, `bigint`, `boolean`, or `numeric` (auto-permitted; none of those types can hold source, a diff, or a rationale). `HOSTED_EXEMPTIONS` is empty: every hosted table's columns are covered above.
<!-- END GENERATED HOSTED ALLOWLIST -->

### Exemptions

`HOSTED_EXEMPTIONS = frozenset()`, exactly, closed empty, not a TODO, pinned by
`tests/test_hosted_boundary_enforcement.py::test_hosted_exemptions_is_empty`. `agent_events` and
`model_calls` used to be exempted here: both held jsonb payloads that could carry more than the
boundary allows, because both had live writers and there was nowhere local to point the detail
until `local_store/` existed (Runtime Task 5). Runtime Task 1B (`202608291930_rescope_hosted_
events.sql`) re-scoped both instead of exempting them: `model_calls.request_metadata` and
`response_metadata` are dropped outright, and `agent_events.payload` is now a flat object of
scalar values only, enforced both by the `agent_events_payload_is_flat` CHECK constraint and by
`record_event.serialize_json_object`. Both tables are allowlisted column by column above, the same
as every other hosted table. The set must stay empty; adding a table back here is a regression.

## Local (runner's own machine, `local_store/`, built in Runtime Task 5)

Everything the hosted plane must never see lives here instead, once Task 5 exists:

- **Source and diffs** - the actual PR content pulled from GitHub.
- **Embeddings** - vector chunks of that source (`code_chunks`, retired hosted-side by this task).
- **Findings and rationale** - the review output itself, including the reasoning behind it
  (`findings`, retired hosted-side by this task).
- **Human decisions** - approve/reject/dispute notes on a finding (`human_decisions`, retired
  hosted-side by this task).
- **Sandbox logs** - verification output that may echo source or diff content.
- **Model API keys** - held in the OS keyring, never transmitted to the control plane.
- **Detailed agent events and per-call model detail** - Runtime Task 1B closed the hosted plane's
  free-form event payload and `model_calls.request_metadata`/`response_metadata` columns; nothing
  had ever written real prompt or output detail through them, so there was no existing detail to
  relocate. Any future prompt/output logging belongs here, in `local_store/`, never on the hosted
  plane, which keeps only a redacted lifecycle event and aggregate token/cost numbers.

## Retired hosted tables (Runtime Task 1A)

Migration 0001 created these on the hosted plane back when the design was a single hosted
service. `<timestamp>_retire_local_only_tables.sql` drops them. All four had zero references
anywhere in `src/` at the time of retirement, so there was no writer to move first:

| Table | Held | Moves to |
|---|---|---|
| `findings` | review findings and rationale | `local_store/` (Task 5) |
| `code_chunks` | source chunks and embeddings | `local_store/` (Task 5) |
| `human_decisions` | human approve/reject/dispute notes on a finding | `local_store/` (Task 5) |
| `pull_requests` | PR identity duplicated from GitHub | `local_store/` (Task 5), if still needed |

`review_jobs.pull_request_id` keeps its column (still read by `claim_review_job`) but lost its
foreign key to `pull_requests`; nothing has ever written it.

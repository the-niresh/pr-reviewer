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

Every column on every hosted table is one of three things: an auto-permitted scalar type that
cannot hold free text, an allowlisted column with a documented reason, or a column on a table in
`HOSTED_EXEMPTIONS`. Anything else fails `assert_no_private_columns`.

<!-- BEGIN GENERATED HOSTED ALLOWLIST -->
| Table | Column | Reason |
|---|---|---|
| `github_deliveries` | `event_name` | GitHub webhook event name, a fixed enum (e.g. pull_request). |
| `github_deliveries` | `id` | GitHub's own delivery id: an opaque identifier, not content. |
| `installations` | `account_login` | GitHub account or org login: a public identifier GitHub itself shows on every page of the installation, not review content. |
| `oauth_states` | `binding_hash` | A one-way hash of the per-attempt binding secret. The secret itself is never stored, so this column cannot be reversed back into it. |
| `oauth_states` | `return_to` | One of our own fixed, allowlisted control-plane paths (see github_oauth.ALLOWED_RETURN_TO_PATHS), validated before this row is ever written. Never a caller-supplied URL, never review content. |
| `oauth_states` | `state_hash` | A one-way hash of the OAuth state value. The state itself is never stored, so this column cannot be reversed back into it. |
| `pairing_codes` | `challenge` | PKCE code_challenge sent by the runner before any human is involved. Not secret, and not reversible to the verifier it was derived from; not review content either way. |
| `pairing_codes` | `code_hash` | A one-way hash of the pairing code. The code itself is never stored, so this column cannot be reversed back into it. |
| `pairing_codes` | `device_name` | Operator-chosen label for the runner device being paired, not review content. |
| `pairing_codes` | `repository_ids` | Our own repositories.id values selected at approval, an array of opaque identifiers, not repository content. |
| `prompt_versions` | `content` | Our own prompt template text, operational config we author ourselves, not a customer's source, diff, or finding. No writer exists yet; unused scaffolding from migration 0001. |
| `prompt_versions` | `name` | Name of one of our own prompt templates, not customer content. |
| `prompt_versions` | `version` | Version label for one of our own prompt templates. |
| `repositories` | `name` | GitHub repository name: an identifier, not repository content. |
| `review_jobs` | `delivery_id` | References github_deliveries.id, an opaque identifier. |
| `review_jobs` | `last_error` | Short operator-facing error string for worker logs and status APIs. Must stay a message or exception class name, never a diff, stack trace, or file content. |
| `review_jobs` | `locked_by` | Worker id holding the current lease, an operational identifier. |
| `review_jobs` | `status` | Fixed enum ('pending', 'running', 'succeeded', 'failed'), enforced by a check constraint. |
| `runners` | `credential_hash` | A one-way hash of the runner's credential. The credential itself is never stored, so this column cannot be reversed back into it. |
| `runners` | `device_name` | Operator-chosen label for a runner device, not review content. |
| `runners` | `mode` | Fixed enum ('analysis_only', 'full'), enforced by a check constraint. |
| `runners` | `platform` | Runner platform identifier (e.g. darwin-arm64), not review content. |
| `runners` | `version` | Runner software version string. |
| `schema_migrations` | `checksum` | sha256 hex digest of a migration file, an opaque hash. |
| `schema_migrations` | `filename` | Our own migration filename: code structure metadata, not review content. |

Every other hosted column is either `uuid`, `timestamptz`, `integer`, `bigint`, `boolean`, or `numeric` (auto-permitted; none of those types can hold source, a diff, or a rationale), or belongs to a table in `HOSTED_EXEMPTIONS` (`agent_events, model_calls`, see below).
<!-- END GENERATED HOSTED ALLOWLIST -->

### Exemptions

`HOSTED_EXEMPTIONS = {"agent_events", "model_calls"}`, exactly, pinned by
`tests/test_hosted_boundary_enforcement.py`. Both tables hold jsonb payloads that today can carry
more than the boundary allows (`agent_events.payload`, `model_calls.request_metadata`,
`model_calls.response_metadata`), because both have live writers and there is nowhere local to
point them until `local_store/` exists (Runtime Task 5). Runtime Task 1B removes both entries once
that writer move happens and re-scopes the hosted shape to redacted lifecycle events and aggregate
cost only. The exemption set must never grow past these two names, and it must end **empty**.

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
- **Detailed agent events and per-call model detail** - once Runtime Task 1B re-scopes the hosted
  writers, the free-form event payload and prompt/output detail move here; the hosted plane keeps
  only a redacted lifecycle event and aggregate token/cost numbers.

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

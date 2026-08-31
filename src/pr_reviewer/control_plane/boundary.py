"""Runtime Task 1A: schema-level enforcement of the hosted data boundary.

docs/DATA_BOUNDARIES.md is the human-readable half of this contract; this module is the enforced
half. assert_no_private_columns reads the live hosted schema, never a hand-maintained table list,
and fails loudly if any column could hold source, a diff, a finding, rationale, a sandbox log, or
an embedding. It is meant to run at process startup and in CI, not on a request path.

Detection is scoped by column TYPE, not by name. A handful of scalar types (uuid, timestamptz,
integer, bigint, boolean, numeric) can never hold free text, so they are auto-permitted. Every
other type -- text, varchar, char, jsonb, bytea, an array of any of those, or anything Postgres
reports as ARRAY or USER-DEFINED -- must carry an explicit ALLOWLIST entry naming the table, the
column, and a reason. A badly-named column, or a pgvector embedding (which information_schema
reports as USER-DEFINED, not as its element type), fails closed instead of slipping past a
name-based check.
"""

from __future__ import annotations

from psycopg import Connection

from pr_reviewer.db.client import Row, connection

AUTO_PERMIT_TYPES = frozenset(
    {"uuid", "timestamp with time zone", "integer", "bigint", "boolean", "numeric"}
)

# Tables that may keep a shape this module would otherwise reject. Runtime Task 1B emptied this:
# agent_events and model_calls used to hold free-form jsonb (a caller-supplied event payload, and
# a request_metadata/response_metadata blob nobody constrained) with nowhere local to point the
# detail until local_store/ existed (Runtime Task 5). Both are now allowlisted narrowly, column by
# column, like every other hosted table -- see agent_events.payload and
# model_calls.provider/model_name below. Staying empty is itself part of the boundary:
# tests/test_hosted_boundary_enforcement.py's test_hosted_exemptions_is_empty fails the moment
# anything is added back.
HOSTED_EXEMPTIONS: frozenset[str] = frozenset()


class HostedSchemaViolation(RuntimeError):
    """Raised when the hosted schema has a column that could hold private review data."""


# (table, column) -> reason. Every entry here becomes a row in the hosted half of
# docs/DATA_BOUNDARIES.md; regenerate that file after editing this list so the two cannot drift.
ALLOWLIST: dict[tuple[str, str], str] = {
    ("agent_events", "event_type"): (
        "Lifecycle event name from a fixed, code-controlled set (e.g. review_job_failed, "
        "model_call.recorded), never derived from repository or review content."
    ),
    ("agent_events", "payload"): (
        "Redacted lifecycle event detail only: identifiers, enums, and aggregate token/cost "
        "numbers. agent_events_payload_is_flat (migration "
        "202608291930_rescope_hosted_events.sql) rejects a nested object or array at the "
        "database layer, and record_event.serialize_json_object rejects one at the application "
        "layer, so this column cannot hold a findings list, a diff, or a sandbox log."
    ),
    ("github_deliveries", "id"): "GitHub's own delivery id: an opaque identifier, not content.",
    ("github_deliveries", "event_name"): (
        "GitHub webhook event name, a fixed enum (e.g. pull_request)."
    ),
    ("installations", "account_login"): (
        "GitHub account or org login: a public identifier GitHub itself shows on every page of "
        "the installation, not review content."
    ),
    ("oauth_states", "state_hash"): (
        "A one-way hash of the OAuth state value. The state itself is never stored, so this "
        "column cannot be reversed back into it."
    ),
    ("oauth_states", "binding_hash"): (
        "A one-way hash of the per-attempt binding secret. The secret itself is never stored, so "
        "this column cannot be reversed back into it."
    ),
    ("oauth_states", "return_to"): (
        "One of our own fixed, allowlisted control-plane paths (see "
        "github_oauth.ALLOWED_RETURN_TO_PATHS), validated before this row is ever written. Never "
        "a caller-supplied URL, never review content."
    ),
    ("pairing_codes", "device_name"): (
        "Operator-chosen label for the runner device being paired, not review content."
    ),
    ("pairing_codes", "code_hash"): (
        "A one-way hash of the pairing code. The code itself is never stored, so this column "
        "cannot be reversed back into it."
    ),
    ("pairing_codes", "challenge"): (
        "PKCE code_challenge sent by the runner before any human is involved. Not secret, and "
        "not reversible to the verifier it was derived from; not review content either way."
    ),
    ("pairing_codes", "repository_ids"): (
        "Our own repositories.id values selected at approval, an array of opaque identifiers, "
        "not repository content."
    ),
    ("model_calls", "provider"): (
        "Fixed enum ('openai', 'anthropic'), an identifier for which model API served the call, "
        "not review content."
    ),
    ("model_calls", "model_name"): (
        "Model name from our own configured model list (e.g. gpt-5-mini), an identifier, not "
        "review content."
    ),
    ("prompt_versions", "name"): "Name of one of our own prompt templates, not customer content.",
    ("prompt_versions", "version"): "Version label for one of our own prompt templates.",
    ("prompt_versions", "content"): (
        "Our own prompt template text, operational config we author ourselves, not a customer's "
        "source, diff, or finding. Insert-only: record_prompt_version writes a new name and "
        "version, and the prompt_versions_immutable_update trigger rejects any UPDATE."
    ),
    ("repositories", "name"): "GitHub repository name: an identifier, not repository content.",
    ("review_jobs", "delivery_id"): "References github_deliveries.id, an opaque identifier.",
    ("review_jobs", "status"): (
        "Fixed enum ('pending', 'running', 'succeeded', 'failed', 'superseded', 'cancelled'), "
        "enforced by a check constraint."
    ),
    ("review_jobs", "locked_by"): "Worker id holding the current lease, an operational identifier.",
    ("review_jobs", "last_error"): (
        "One of ReviewJobErrorClass's fixed values (contracts/errors.py), never a caller-supplied "
        "string: fail_review_job rejects anything else before it reaches this column, so it can "
        "never hold a diff, a stack trace, or file content."
    ),
    ("review_jobs", "base_sha"): ("GitHub base commit SHA: an identifier, not repository content."),
    ("review_jobs", "head_sha"): ("GitHub head commit SHA: an identifier, not repository content."),
    ("review_jobs", "policy_version"): (
        "Our own policy version label applied to the job, operational config, not review content."
    ),
    ("review_jobs", "lease_token_hash"): (
        "A one-way hash of the job lease token. The token itself is never stored, so this column "
        "cannot be reversed back into it."
    ),
    ("runners", "device_name"): "Operator-chosen label for a runner device, not review content.",
    ("runners", "credential_hash"): (
        "A one-way hash of the runner's credential. The credential itself is never stored, so "
        "this column cannot be reversed back into it."
    ),
    ("runners", "mode"): "Fixed enum ('analysis_only', 'full'), enforced by a check constraint.",
    ("runners", "platform"): "Runner platform identifier (e.g. darwin-arm64), not review content.",
    ("runners", "version"): "Runner software version string.",
    ("schema_migrations", "filename"): (
        "Our own migration filename: code structure metadata, not review content."
    ),
    ("schema_migrations", "checksum"): "sha256 hex digest of a migration file, an opaque hash.",
    ("connector_runs", "connector"): (
        "Fixed enum ('github'), the outbound API this row audited, not review content."
    ),
    ("connector_runs", "operation"): (
        "Fixed enum ('create_installation_token', 'fetch_pull_request', "
        "'create_pull_request_review'), the named call that ran, not a request or response body."
    ),
    ("connector_runs", "external_id"): (
        "Opaque GitHub request identifier when one is present. Typed and redacted so it cannot "
        "hold a token, a header, or a payload."
    ),
    ("connector_runs", "payload_hash"): (
        "sha256 hex of operation, status, and byte counts only. The payload itself is never "
        "stored; this hash cannot be reversed into a body, a token, or a patch."
    ),
    ("notification_channels", "name"): (
        "Operator-chosen label for a notification destination, not review content."
    ),
    ("notification_channels", "transport"): (
        "Fixed enum ('slack', 'telegram', 'discord'), the outbound transport, not a webhook URL "
        "and not review content."
    ),
    ("notification_channels", "confidentiality"): (
        "Fixed enum ('restricted', 'ordinary') declared by the operator. Default is restricted. "
        "Never inferred from the transport, never a finding title."
    ),
    ("notification_channels", "purpose"): (
        "Fixed enum ('security_alert', 'review_ping'), which job this channel may carry, not "
        "review content."
    ),
    ("notification_channels", "endpoint_hash"): (
        "A one-way hash of the webhook URL. The URL itself is never stored, so this column "
        "cannot be reversed back into it."
    ),
}


def assert_no_private_columns(conn: Connection[Row] | None = None) -> None:
    """Fail loudly if the hosted schema can physically hold private review data.

    Reads information_schema directly, so a table that is renamed, added, or given a new column
    is caught the next time this runs, without anyone updating a hand-maintained list.
    """
    if conn is not None:
        _assert_no_private_columns(conn)
        return

    with connection() as pooled_conn:
        _assert_no_private_columns(pooled_conn)


def _assert_no_private_columns(conn: Connection[Row]) -> None:
    rows = conn.execute(
        """
        select c.table_name, c.column_name, c.data_type
        from information_schema.columns c
        join information_schema.tables t
          on t.table_schema = c.table_schema and t.table_name = c.table_name
        where c.table_schema = 'public' and t.table_type = 'BASE TABLE'
        order by c.table_name, c.ordinal_position
        """
    ).fetchall()

    violations: list[str] = []
    for row in rows:
        table_name = str(row["table_name"])
        column_name = str(row["column_name"])
        data_type = str(row["data_type"])
        if table_name in HOSTED_EXEMPTIONS:
            continue
        if data_type in AUTO_PERMIT_TYPES:
            continue
        if (table_name, column_name) in ALLOWLIST:
            continue
        violations.append(f"{table_name}.{column_name} ({data_type})")

    if violations:
        raise HostedSchemaViolation(
            "hosted schema has column(s) that could hold private review data, with no allowlist "
            "entry and no exemption: " + ", ".join(violations)
        )

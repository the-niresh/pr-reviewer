-- Local runner state (Runtime Task 5). Lives entirely on the runner's own machine: source, diffs,
-- review findings, rationale, and human decision notes never touch the hosted control plane. This
-- is where Task 1A pointed when it retired the hosted findings, code_chunks, human_decisions, and
-- pull_requests tables -- the field shapes below mirror those tables' columns on purpose.
--
-- lease_token is stored in the clear on local_jobs. That is a deliberate exception to "no secret
-- in SQLite": it is a short-lived, per-job capability the runner needs to heartbeat or acknowledge
-- the same job again after a restart, not a long-lived credential like the runner credential,
-- model keys, GitHub tokens, or the Slack secret, none of which have a column anywhere in this
-- file. Holding lease_token still makes this file a capability store, so open_local_store enforces
-- file mode 0600 and directory mode 0700 (tests/test_local_store.py), the same as
-- runner/secrets.py's FileSecretStore.
--
-- Every local_events row carries trace_id and a per-store sequence (the table's own autoincrement
-- rowid, a single counter across every job, not scoped per job) so Task 5A can join a hosted
-- agent_events row to the local events it caused.

create table local_jobs (
  job_id text primary key,
  installation_id integer not null,
  repository_id integer not null,
  pull_request_number integer not null,
  base_sha text not null,
  head_sha text not null,
  policy_version text not null,
  budget_max_tokens integer not null,
  budget_max_cost_usd text not null,
  trace_id text not null,
  lease_token text not null,
  status text not null check (status in ('claimed', 'completed', 'abandoned')),
  claimed_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

create index local_jobs_status_idx on local_jobs (status);

create table local_snapshots (
  job_id text primary key references local_jobs (job_id),
  repo_owner text not null,
  repo_name text not null,
  number integer not null check (number > 0),
  base_sha text not null,
  head_sha text not null,
  title text not null,
  body text not null,
  files_json text not null,
  fetched_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

create table local_findings (
  id text primary key,
  job_id text not null references local_jobs (job_id),
  concern text not null
    check (concern in ('security', 'correctness', 'tests', 'docs', 'maintainability')),
  severity text not null check (severity in ('critical', 'high', 'medium', 'low', 'info')),
  category text not null,
  file_path text not null,
  line_start integer not null check (line_start > 0),
  line_end integer not null check (line_end >= line_start),
  title text not null,
  rationale text not null,
  evidence_json text not null,
  confidence real not null check (confidence >= 0 and confidence <= 1),
  verified integer not null check (verified in (0, 1)),
  verification_method text not null
    check (verification_method in ('sandbox', 'static', 'not_applicable', 'failed')),
  public_safe integer not null check (public_safe in (0, 1)),
  status text not null
    check (status in ('draft', 'queued_for_human', 'posted', 'rejected', 'disputed')),
  created_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

create index local_findings_job_idx on local_findings (job_id, created_at);

create table local_human_decisions (
  id integer primary key autoincrement,
  finding_id text not null references local_findings (id),
  decision text not null check (decision in ('approved', 'rejected', 'disputed')),
  decided_by text not null,
  note text,
  created_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

create index local_human_decisions_finding_idx on local_human_decisions (finding_id, created_at);

create table local_events (
  sequence integer primary key autoincrement,
  job_id text,
  trace_id text not null,
  event_type text not null,
  payload_json text not null,
  created_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

create index local_events_job_idx on local_events (job_id, sequence);

create table local_pending_acknowledgements (
  id integer primary key autoincrement,
  job_id text not null references local_jobs (job_id),
  lease_token text not null,
  result_json text not null,
  reason text not null check (reason in ('invalid_or_expired', 'network_unreachable')),
  attempts integer not null default 0 check (attempts >= 0),
  created_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

create index local_pending_acknowledgements_job_idx on local_pending_acknowledgements (job_id);

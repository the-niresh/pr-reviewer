-- Master Task 8: hosted connector audit log. Every row carries the job trace_id so
-- Task 8A can join this table later. The shape cannot hold a body, payload, headers,
-- request, response, token, or authorization: only identifiers, byte counts, and a
-- hash of metadata. HOSTED_EXEMPTIONS stays empty; new text columns are allowlisted
-- in control_plane.boundary.

create table connector_runs (
  id uuid primary key default gen_random_uuid(),
  review_job_id uuid references review_jobs(id) on delete cascade,
  trace_id uuid not null,
  connector text not null check (connector in ('github')),
  operation text not null
    check (operation in ('create_installation_token', 'fetch_pull_request')),
  external_id text,
  request_bytes integer not null check (request_bytes >= 0),
  response_bytes integer not null check (response_bytes >= 0),
  payload_hash text not null check (payload_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now()
);

create index connector_runs_trace_id_idx on connector_runs (trace_id);
create index connector_runs_review_job_id_idx on connector_runs (review_job_id);

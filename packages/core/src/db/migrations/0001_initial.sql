create extension if not exists vector;
create extension if not exists pgcrypto;

create table github_deliveries (
  id text primary key,
  event_name text not null,
  received_at timestamptz not null default now()
);

create table pull_requests (
  id uuid primary key default gen_random_uuid(),
  repository_owner text not null,
  repository_name text not null,
  number integer not null check (number > 0),
  title text,
  head_sha text,
  base_sha text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (repository_owner, repository_name, number)
);

create table review_jobs (
  id uuid primary key default gen_random_uuid(),
  delivery_id text not null references github_deliveries(id),
  pull_request_id uuid references pull_requests(id),
  status text not null check (status in ('pending', 'running', 'succeeded', 'failed')),
  attempts integer not null default 0 check (attempts >= 0),
  available_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index review_jobs_available_idx on review_jobs (available_at, created_at)
  where status = 'pending';

create table findings (
  id text primary key,
  review_job_id uuid not null references review_jobs(id),
  concern text not null check (concern in ('security', 'correctness', 'tests', 'docs', 'maintainability')),
  severity text not null check (severity in ('critical', 'high', 'medium', 'low', 'info')),
  category text not null,
  file_path text not null,
  line_start integer not null check (line_start > 0),
  line_end integer not null check (line_end >= line_start),
  title text not null,
  rationale text not null,
  evidence jsonb not null check (jsonb_typeof(evidence) = 'array' and jsonb_array_length(evidence) > 0),
  confidence numeric(4, 3) not null check (confidence >= 0 and confidence <= 1),
  verified boolean not null,
  verification_method text not null check (verification_method in ('sandbox', 'static', 'not_applicable', 'failed')),
  public_safe boolean not null,
  status text not null check (status in ('draft', 'queued_for_human', 'posted', 'rejected', 'disputed')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index findings_review_job_idx on findings (review_job_id, created_at);

create table code_chunks (
  id uuid primary key default gen_random_uuid(),
  pull_request_id uuid references pull_requests(id),
  repository_owner text not null,
  repository_name text not null,
  commit_sha text not null,
  file_path text not null,
  start_line integer not null check (start_line > 0),
  end_line integer not null check (end_line >= start_line),
  content text not null,
  content_hash text not null,
  embedding vector(1536),
  created_at timestamptz not null default now(),
  unique (repository_owner, repository_name, commit_sha, file_path, start_line, end_line, content_hash)
);

create index code_chunks_repository_idx on code_chunks (repository_owner, repository_name, commit_sha);

create table prompt_versions (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  version text not null,
  content text not null,
  created_at timestamptz not null default now(),
  unique (name, version)
);

create table model_calls (
  id uuid primary key default gen_random_uuid(),
  review_job_id uuid not null references review_jobs(id),
  prompt_version_id uuid references prompt_versions(id),
  provider text not null,
  model_name text not null,
  input_tokens integer not null default 0 check (input_tokens >= 0),
  output_tokens integer not null default 0 check (output_tokens >= 0),
  cost_usd numeric(12, 6) not null default 0 check (cost_usd >= 0),
  request_metadata jsonb not null default '{}',
  response_metadata jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create index model_calls_review_job_idx on model_calls (review_job_id, created_at);

create table human_decisions (
  id uuid primary key default gen_random_uuid(),
  finding_id text not null references findings(id),
  decision text not null check (decision in ('approved', 'rejected', 'disputed')),
  decided_by text not null,
  note text,
  created_at timestamptz not null default now()
);

create index human_decisions_finding_idx on human_decisions (finding_id, created_at);

create table agent_events (
  id uuid primary key default gen_random_uuid(),
  review_job_id uuid references review_jobs(id),
  event_type text not null,
  payload jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create index agent_events_review_job_idx on agent_events (review_job_id, created_at);

create function reject_append_only_mutation() returns trigger
language plpgsql
as $$
begin
  raise exception '% rows are append-only', tg_table_name;
end;
$$;

create trigger human_decisions_append_only
before update or delete on human_decisions
for each row execute function reject_append_only_mutation();

create trigger agent_events_append_only
before update or delete on agent_events
for each row execute function reject_append_only_mutation();

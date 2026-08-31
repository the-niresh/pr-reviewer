-- Local finding_candidates. Model-owned fields only.
-- System code assigns candidate_pk and job_id.
-- Lives only on the runner's Postgres. Hosted Neon must never grow these tables.

create table if not exists finding_candidates (
  candidate_pk uuid primary key default gen_random_uuid(),
  job_id text not null,
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
  created_at timestamptz not null default now()
);

create index if not exists finding_candidates_job_idx
  on finding_candidates (job_id, created_at);

create table if not exists finding_verifications (
  candidate_pk uuid not null references finding_candidates (candidate_pk),
  method text not null check (method in ('sandbox', 'static', 'not_applicable', 'failed')),
  outcome text not null check (outcome in ('passed', 'failed', 'inconclusive', 'not_applicable')),
  created_at timestamptz not null default now()
);

create index if not exists finding_verifications_candidate_idx
  on finding_verifications (candidate_pk, created_at);

-- Phase 27 deliberately widens the Phase 2 data boundary (docs/DATA_BOUNDARIES.md): the web
-- dashboard needs findings text and per-agent reasoning, so this migration gives them a narrow,
-- explicit home on the hosted plane. Named review_findings, not findings, so it is not the same
-- table Runtime Task 1A retired in 202608281326_retire_local_only_tables.sql -- that retirement
-- and its tests (test_hosted_boundary_enforcement.py) stay intact and unmodified.
--
-- Deliberately excluded: evidence. The old findings table stored it as a jsonb array of
-- freeform strings with no constraint on what goes in each one, and it is not named in
-- requirements.md's "What reaches the server" list, unlike title/rationale/category/severity/
-- file_path/line numbers. Until evidence has a typed, audited shape, it stays local-only with
-- the diff hunks and sandbox logs it could otherwise smuggle.
--
-- Every text and jsonb column added here gets a matching entry in
-- src/pr_reviewer/control_plane/boundary.py's ALLOWLIST in the same commit, with a written
-- reason; assert_no_private_columns fails closed on anything that is missing one.

create table review_findings (
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
  confidence numeric(4, 3) not null check (confidence >= 0 and confidence <= 1),
  verified boolean not null,
  verification_method text not null check (verification_method in ('sandbox', 'static', 'not_applicable', 'failed')),
  public_safe boolean not null,
  status text not null check (status in ('draft', 'queued_for_human', 'posted', 'rejected', 'disputed')),
  created_at timestamptz not null default now()
);

create index review_findings_review_job_idx on review_findings (review_job_id, created_at);

create table agent_reasoning (
  id uuid primary key default gen_random_uuid(),
  review_job_id uuid not null references review_jobs(id),
  concern text not null check (concern in ('security', 'correctness', 'tests', 'docs', 'maintainability')),
  reasoning text not null,
  created_at timestamptz not null default now()
);

create index agent_reasoning_review_job_idx on agent_reasoning (review_job_id, created_at);

create trigger review_findings_append_only
before update or delete on review_findings
for each row execute function reject_append_only_mutation();

create trigger agent_reasoning_append_only
before update or delete on agent_reasoning
for each row execute function reject_append_only_mutation();

-- Runtime Task 3: outbound job claim. review_jobs grows the identifiers a runner needs on a
-- JobEnvelope (installation, numeric repository, PR number, SHAs, policy, budget, trace) and the
-- lease_token_hash that binds a claim to one runner. The plaintext lease token is returned once
-- at claim and never stored, matching runners.credential_hash.
--
-- status gains 'superseded' so a newer head SHA can retire an older pending or running job
-- without looking like a worker failure. Identity columns are nullable because existing enqueue
-- paths (tests and webhooks that carry no pull_request payload) still insert a pending row with
-- only a delivery_id; runner claim_job ignores those rows because they cannot be assigned.
alter table review_jobs drop constraint review_jobs_status_check;
alter table review_jobs add constraint review_jobs_status_check
  check (status in ('pending', 'running', 'succeeded', 'failed', 'superseded'));

alter table review_jobs
  add column installation_id bigint references installations(id),
  add column github_repository_id bigint,
  add column pull_request_number integer check (pull_request_number is null or pull_request_number > 0),
  add column base_sha text,
  add column head_sha text,
  add column policy_version text,
  add column budget_max_tokens integer check (budget_max_tokens is null or budget_max_tokens >= 0),
  add column budget_max_cost_usd numeric(12, 6) check (budget_max_cost_usd is null or budget_max_cost_usd >= 0),
  add column trace_id uuid,
  add column lease_token_hash text;

create index review_jobs_runner_claim_idx
  on review_jobs (installation_id, github_repository_id, pull_request_number, status)
  where status in ('pending', 'running');

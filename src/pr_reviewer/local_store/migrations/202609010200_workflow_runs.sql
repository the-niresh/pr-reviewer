-- Local workflow step state (master Task 16). Lives on the runner, next to local_jobs.
-- review_jobs on the hosted plane stays queue state (pending/running/succeeded/failed/
-- superseded/cancelled). This table must not grow those queue values: outcome is null
-- until the engine finishes, then one of completed, cancelled, or failed. A crash leaves
-- outcome null and completed steps in workflow_steps, which is how resume knows where
-- to continue without asking the queue whether the job is "running".

create table workflow_runs (
  workflow_id text primary key,
  job_id text not null,
  head_sha text not null,
  trace_id text not null,
  lease_token text not null default '',
  input_json text not null,
  outcome text check (outcome is null or outcome in ('completed', 'cancelled', 'failed')),
  reason text,
  created_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

create index workflow_runs_job_idx on workflow_runs (job_id);

create table workflow_steps (
  workflow_id text not null references workflow_runs (workflow_id),
  step_name text not null,
  effect_hash text,
  output_json text not null,
  completed_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  primary key (workflow_id, step_name)
);

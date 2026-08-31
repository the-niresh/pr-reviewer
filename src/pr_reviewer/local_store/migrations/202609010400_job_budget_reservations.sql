create table local_job_budgets (
  job_id text primary key references local_jobs (job_id),
  reserved_tokens integer not null default 0 check (reserved_tokens >= 0),
  reserved_cost_usd text not null default '0'
);

-- Master Task 18: repository budgets, per-job reservations, and connector circuits.
-- Unset limits (null or zero) deny spend. Finding text is not a column here.

create table repository_budgets (
  installation_id bigint not null references installations(id),
  github_repository_id bigint not null,
  max_tokens integer,
  max_cost_usd numeric(18, 6),
  reserved_tokens integer not null default 0 check (reserved_tokens >= 0),
  reserved_cost_usd numeric(18, 6) not null default 0 check (reserved_cost_usd >= 0),
  spent_tokens integer not null default 0 check (spent_tokens >= 0),
  spent_cost_usd numeric(18, 6) not null default 0 check (spent_cost_usd >= 0),
  primary key (installation_id, github_repository_id)
);

create table repository_budget_reservations (
  job_id uuid primary key,
  installation_id bigint not null,
  github_repository_id bigint not null,
  tokens integer not null check (tokens >= 0),
  cost_usd numeric(18, 6) not null check (cost_usd >= 0),
  status text not null check (status in ('held', 'released', 'committed'))
);

create index repository_budget_reservations_repo_idx
  on repository_budget_reservations (installation_id, github_repository_id);

create table connector_circuits (
  connector text not null primary key,
  state text not null check (state in ('closed', 'open', 'half_open')),
  consecutive_failures integer not null default 0 check (consecutive_failures >= 0),
  probe_after timestamptz,
  last_error_kind text
);

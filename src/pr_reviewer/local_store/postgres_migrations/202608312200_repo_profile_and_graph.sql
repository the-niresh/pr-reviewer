-- Local repository profiles and graph snapshot metadata (master Task 13A).
-- Lives only on the runner's Postgres. Hosted Neon must never grow these tables.
-- A profile summarises private source, so it never reaches the control plane.

create table if not exists repo_profiles (
  id uuid primary key default gen_random_uuid(),
  installation_id integer not null default 0,
  repository_id integer not null,
  commit_sha text not null,
  model_name text not null,
  prompt_version text not null,
  generated_at timestamptz not null,
  content_hash text not null,
  created_at timestamptz not null default now()
);

create index if not exists repo_profiles_repository_idx
  on repo_profiles (repository_id, generated_at desc);

create table if not exists profile_claims (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references repo_profiles (id),
  kind text not null,
  text text not null,
  supporting_paths text[] not null default '{}',
  status text not null check (status in ('candidate', 'promoted')),
  retired_at timestamptz
);

create index if not exists profile_claims_profile_idx
  on profile_claims (profile_id, status);

create table if not exists code_graph_snapshots (
  id uuid primary key default gen_random_uuid(),
  repository_id integer not null,
  commit_sha text not null,
  extracted_edge_count integer not null,
  inferred_edge_count integer not null,
  content_hash text not null,
  created_at timestamptz not null default now()
);

create index if not exists code_graph_snapshots_repository_idx
  on code_graph_snapshots (repository_id, created_at desc);

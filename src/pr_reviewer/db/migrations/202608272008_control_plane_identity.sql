-- Identity is the numeric GitHub installation ID and repository ID, never a display name.
-- github_repository_id is not made globally unique here: a repository transfer between
-- installations must be able to register a second row for the same numeric ID, under the new
-- installation, without disturbing the old installation's row.

create table installations (
  id bigint primary key,
  account_login text not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

create table repositories (
  id uuid primary key default gen_random_uuid(),
  installation_id bigint not null references installations(id),
  github_repository_id bigint not null,
  name text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (installation_id, github_repository_id)
);

create index repositories_github_repository_id_idx on repositories (github_repository_id);

create table runners (
  id uuid primary key default gen_random_uuid(),
  device_name text not null,
  credential_hash text not null,
  mode text not null check (mode in ('analysis_only', 'full')),
  docker_available boolean not null default false,
  retrieval_available boolean not null default false,
  verification_available boolean not null default false,
  platform text not null,
  version text not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

-- One active assignment per repository. A runner may hold more than one repository.
create table repository_assignments (
  id uuid primary key default gen_random_uuid(),
  repository_id uuid not null references repositories(id),
  runner_id uuid not null references runners(id),
  created_at timestamptz not null default now(),
  unique (repository_id)
);

create index repository_assignments_runner_idx on repository_assignments (runner_id);

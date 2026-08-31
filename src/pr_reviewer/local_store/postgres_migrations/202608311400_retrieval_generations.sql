-- Local pgvector schema for retrieval generations (master Task 12).
-- Lives only on the runner's Postgres. Hosted Neon must never grow these tables.
-- Model name and dimensions sit on the generation so mixed embeddings cannot
-- share a row. vector(1536) and check (dimensions = 1536) are the v1 contract.
-- Exact scan first: no approximate vector index. tsvector + GIN is for lexical search.

create table if not exists embedding_generations (
  id uuid primary key default gen_random_uuid(),
  installation_id integer not null,
  repository_id integer not null,
  commit_sha text not null,
  model_name text not null,
  dimensions integer not null check (dimensions = 1536),
  state text not null check (state in ('building', 'active', 'retired')),
  created_at timestamptz not null default now()
);

create unique index if not exists embedding_generations_one_active
  on embedding_generations (installation_id, repository_id)
  where state = 'active';

create table if not exists code_chunks (
  id uuid primary key default gen_random_uuid(),
  generation_id uuid not null references embedding_generations (id),
  file_path text not null,
  language text not null,
  start_line integer not null check (start_line > 0),
  end_line integer not null check (end_line >= start_line),
  content text not null,
  content_hash text not null,
  identity text not null,
  strategy text not null check (strategy in ('ast_python', 'line_window')),
  symbol_name text,
  embedding vector(1536) not null,
  content_tsv tsvector generated always as (to_tsvector('simple', content)) stored,
  created_at timestamptz not null default now()
);

create index if not exists code_chunks_generation_idx on code_chunks (generation_id);
create unique index if not exists code_chunks_generation_identity_idx
  on code_chunks (generation_id, identity);
create index if not exists code_chunks_content_tsv_gin on code_chunks using gin (content_tsv);

-- Runtime Task 2: one-time runner pairing. One new table holds the whole lifecycle of a pairing
-- code from creation through approval to exchange; there is no separate approvals or exchanges
-- table because a pairing code has exactly one of each, ever.
--
-- code_hash is a one-way hash of the pairing code (tests/test_runner_pairing.py asserts this exact
-- column name). The plaintext code is never stored, matching runners.credential_hash.
--
-- challenge is the PKCE code_challenge the runner sent at creation, before any human is involved.
-- It is not secret (PKCE challenges never are); what makes exchange safe is that only the runner
-- holding the matching verifier can produce a value that hashes back to it.
--
-- installation_id and repository_ids are set once, at approval, and never change afterwards.
-- installation_id is nullable because a code that has not been approved yet has neither. There is
-- no foreign key from repository_ids to repositories: approval upserts each selected repository
-- and records the resulting ids here, so by the time this column is non-null every id in it is
-- already a valid repositories.id, without needing a constraint postgres cannot express over an
-- array anyway.
--
-- What marks a code consumed is exchanged_at: a code with exchanged_at set has already produced
-- its one credential and can never produce another. approved_at is separate from exchanged_at
-- because a pairing can be approved and then abandoned (tab closed, runner host dies, code
-- expires) without ever being exchanged; its repositories must not be permanently unclaimable
-- just because approval happened. Expiry itself is not a stored timestamp: it is always computed
-- from created_at, so backdating created_at in a test is enough to simulate it, and there is
-- nothing to keep in sync between two timestamp columns that mean the same ten minutes.
create table pairing_codes (
  id uuid primary key default gen_random_uuid(),
  device_name text not null,
  code_hash text not null unique,
  challenge text not null,
  installation_id bigint references installations(id),
  repository_ids uuid[],
  approved_at timestamptz,
  exchanged_at timestamptz,
  created_at timestamptz not null default now()
);

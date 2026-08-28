-- Runtime Task 2A: hosted GitHub sign-in. One table holds the CSRF state for a single sign-in
-- attempt, from begin_sign_in through the one atomic consume in complete_sign_in.
--
-- state_hash and binding_hash are one-way hashes (tests/test_github_oauth.py backdates rows by
-- recomputing state_hash, so this column name is load-bearing). The plaintext state and
-- binding_secret are never stored, matching runners.credential_hash and pairing_codes.code_hash.
-- state travels in the GitHub authorize URL, where an attacker can see and replay it;
-- binding_secret travels only in an HttpOnly cookie, which never appears in a URL. Neither one
-- alone is enough to complete a sign-in: complete_sign_in consumes both hashes together in a
-- single statement, so a valid state without the matching binding_secret is rejected the same way
-- a state nobody ever issued is.
--
-- return_to is validated against a fixed allowlist before this row is ever written (see
-- github_oauth.ALLOWED_RETURN_TO_PATHS), so by the time it is read back at the callback it is
-- already known safe to redirect to; storing it lets the callback recover it without trusting
-- whatever return_to a caller attaches to the callback request itself.
--
-- consumed_at marks a state used; a row with consumed_at already set can never be consumed again.
-- Expiry is not a stored timestamp, the same choice pairing_codes made: it is always computed from
-- created_at, so backdating created_at in a test is enough to simulate it.
create table oauth_states (
  id uuid primary key default gen_random_uuid(),
  state_hash text not null unique,
  binding_hash text not null,
  return_to text not null,
  consumed_at timestamptz,
  created_at timestamptz not null default now()
);

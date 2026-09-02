-- A runner is paired to one verified GitHub user and one installation. Store that identity with
-- the runner so its authenticated installation snapshot has no dependency on an expired browser
-- sign-in cookie.
alter table runners
  add column github_user_id bigint,
  add column installation_id bigint references installations(id),
  add constraint runners_pairing_identity_check check (
    (github_user_id is null and installation_id is null)
    or (github_user_id is not null and installation_id is not null)
  );

alter table pairing_codes
  add column github_user_id bigint;

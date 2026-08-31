-- Master Task 10: prompt_versions rows are insert-only. unique (name, version) already
-- rejects a second insert. This trigger rejects an UPDATE, so content cannot be rewritten
-- in place. HOSTED_EXEMPTIONS stays empty; no new columns.

create function reject_prompt_version_update()
returns trigger
language plpgsql
as $$
begin
  raise exception 'prompt_versions rows are immutable';
end;
$$;

create trigger prompt_versions_immutable_update
  before update on prompt_versions
  for each row
  execute function reject_prompt_version_update();

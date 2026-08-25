alter table review_jobs
  add column locked_by text,
  add column locked_until timestamptz,
  add column last_error text;

update review_jobs
set status = 'pending', locked_by = null, locked_until = null, available_at = now(), updated_at = now()
where status = 'running';

create index review_jobs_lease_claim_idx
  on review_jobs (status, available_at, locked_until, created_at)
  where status in ('pending', 'running');

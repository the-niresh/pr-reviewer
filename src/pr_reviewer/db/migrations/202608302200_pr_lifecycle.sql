-- Master Task 7: PR lifecycle safety. Installation and numeric repository IDs already
-- exist on review_jobs (202608290208_runner_job_leases.sql). This file does not rewrite
-- those columns. It adds cancelled so closed and converted_to_draft can retire a job
-- without looking like a worker failure, records draft so an opened draft is distinct
-- from ready_for_review, and makes one active job per repository, PR number, and head
-- SHA a database fact. enqueue_review_job already supersedes older pending/running rows
-- for the same PR; the unique index below is the lock, not a second supersede path.

alter table review_jobs drop constraint review_jobs_status_check;
alter table review_jobs add constraint review_jobs_status_check
  check (status in ('pending', 'running', 'succeeded', 'failed', 'superseded', 'cancelled'));

alter table review_jobs
  add column draft boolean;

create unique index review_jobs_one_active_head_idx
  on review_jobs (installation_id, github_repository_id, pull_request_number, head_sha)
  where status in ('pending', 'running')
    and installation_id is not null
    and github_repository_id is not null
    and pull_request_number is not null
    and head_sha is not null;

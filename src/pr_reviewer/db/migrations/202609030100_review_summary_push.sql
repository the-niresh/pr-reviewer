-- Task 33.A4: the TUI now runs a review directly from the terminal and pushes a findings-only
-- summary when it finishes (src/pr_reviewer/tui/push_review_summary.py). That review has no
-- GitHub webhook delivery behind it, so delivery_id must stop being mandatory. The existing
-- queue-driven path (jobs/enqueue_review_job.py) still always supplies one; this only widens
-- what is allowed, it does not change that path.
alter table review_jobs alter column delivery_id drop not null;

-- 'completed' and 'stopped_early' are the two terminal states a pushed summary can carry.
-- 'stopped_early' must stay a distinct status, never folded into 'completed', so the web
-- dashboard can never show a review that ran out of provider tokens partway through as finished.
alter table review_jobs drop constraint review_jobs_status_check;
alter table review_jobs add constraint review_jobs_status_check
  check (status in (
    'pending', 'running', 'succeeded', 'failed', 'superseded', 'cancelled',
    'completed', 'stopped_early'
  ));

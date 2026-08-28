-- Runtime Task 1A retires the tables migration 0001 put on the hosted plane back when this was a
-- single hosted service: findings, code_chunks, human_decisions, pull_requests. The approved data
-- boundary (docs/DATA_BOUNDARIES.md) forbids the hosted control plane from holding source, diffs,
-- review findings, rationale, or human decision notes, so a compromised control plane cannot hand
-- an attacker any of that. Task 5 gives each of these a home in local_store/ on the runner's own
-- machine. Immutable migrations means never edit 0001, not never drop what it made, so this is a
-- new migration rather than a rewrite of the old one.
--
-- agent_events and model_calls are NOT touched here even though they hold jsonb payloads. They
-- have live writers today and no local store exists until Task 5, so control_plane/boundary.py's
-- HOSTED_EXEMPTIONS names them explicitly: Task 1B has to come back for them on purpose, not
-- because this migration missed them.
--
-- All four tables have zero references anywhere in src/, confirmed by
-- tests/test_hosted_boundary_enforcement.py, so this is safe to run today with no writer to move
-- first.

-- human_decisions references findings; drop it first so findings has no dependents left.
drop table human_decisions;

drop table findings;

-- code_chunks references pull_requests; drop it before pull_requests.
drop table code_chunks;

-- review_jobs.pull_request_id is the only other reference to pull_requests. No writer has ever
-- set it (enqueue_review_job only sets delivery_id and status), but claim_review_job still reads
-- it, so only the now-dangling foreign key is dropped here, not the column itself.
alter table review_jobs drop constraint review_jobs_pull_request_id_fkey;

drop table pull_requests;

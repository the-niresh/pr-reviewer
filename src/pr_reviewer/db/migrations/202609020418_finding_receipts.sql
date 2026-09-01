-- Phase 30: the web dashboard shows the same provenance receipt as the TUI for each finding
-- (src/pr_reviewer/reviewer/receipt.py). model_call_id references the model_calls row that
-- produced this finding, so provider/model/tokens/cost/prompt_version_id are derived by join
-- rather than duplicated; only the verification detail and context sources need new columns.
--
-- The receipt.py:115 rule (verified=true only ever cites a real sandbox run) is enforced in
-- Python before a Finding reaches project_review; these columns just carry whichever half of
-- ReceiptVerification that check already approved. sandbox_run_id and command_id are opaque
-- identifiers; verification_reason and verification_detail are short human-authored summaries
-- (test_receipt_verified_means_ran.py shows "sandbox command exited 0", "static checks
-- passed" -- never a raw command log).
--
-- Every text column here gets a matching ALLOWLIST entry in control_plane/boundary.py in the
-- same commit, with a written reason.

alter table review_findings
  add column model_call_id uuid references model_calls(id),
  add column verification_reason text,
  add column sandbox_run_id text,
  add column command_id text,
  add column verification_detail text;

create table finding_context_sources (
  id uuid primary key default gen_random_uuid(),
  finding_id text not null references review_findings(id),
  kind text not null check (kind in ('diff', 'retrieval', 'profile', 'graph')),
  name text not null,
  reference text not null,
  created_at timestamptz not null default now()
);

create index finding_context_sources_finding_idx on finding_context_sources (finding_id);

create trigger finding_context_sources_append_only
before update or delete on finding_context_sources
for each row execute function reject_append_only_mutation();

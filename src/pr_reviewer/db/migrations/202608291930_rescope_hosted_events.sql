-- Runtime Task 1B re-scopes agent_events and model_calls to the boundary the docs always
-- promised, and empties HOSTED_EXEMPTIONS (control_plane/boundary.py) for good. Task 1A could not
-- retire the free-form shape of these two tables in the same pass as findings/code_chunks/
-- human_decisions/pull_requests: both had live writers and there was nowhere local to point the
-- detail until local_store/ existed (Runtime Task 5, now built).
--
-- model_calls.request_metadata and response_metadata are dropped outright, not narrowed.
-- request_metadata was the one column a caller could actually fill with anything --
-- ModelCallInput.metadata was a free JsonObject, so a prompt or a full model output could have
-- landed here. response_metadata was written by nobody, ever, in this table's history. Neither
-- survives; a model call's hosted row now carries only identifiers and aggregate token/cost/
-- latency numbers, never a prompt, an output, or a hash of one.
--
-- agent_events.payload keeps its jsonb column -- a lifecycle event genuinely needs a handful of
-- named fields per event type -- but agent_events_payload_is_flat makes "flat object, scalar
-- values only" a database-enforced fact, not a convention record_event.py's callers are trusted
-- to follow. A compromised control plane cannot use this column to smuggle a nested findings
-- list, a diff, or a sandbox log, because the database itself refuses to store one.

alter table model_calls
  drop column request_metadata,
  drop column response_metadata;

-- A CHECK constraint cannot contain a subquery (jsonb_each + EXISTS), so this uses a jsonpath
-- filter instead. "strict" mode matters: in the default lax mode, applying .type() to an array
-- value auto-unwraps it into its elements first, so an array value's own type would never match
-- and a top-level array could slip through unflagged.
alter table agent_events
  add constraint agent_events_payload_is_flat check (
    jsonb_typeof(payload) = 'object'
    and not jsonb_path_exists(payload, 'strict $.* ? (@.type() == "object" || @.type() == "array")')
  );

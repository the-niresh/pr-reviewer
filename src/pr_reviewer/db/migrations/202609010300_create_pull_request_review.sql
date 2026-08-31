-- Master Task 17: posting is a named GitHub connector operation. The audit row still
-- stores only identifiers, byte counts, and a hash of those metadata fields. Finding
-- text is not a column here.

alter table connector_runs drop constraint connector_runs_operation_check;
alter table connector_runs add constraint connector_runs_operation_check
  check (operation in (
    'create_installation_token',
    'fetch_pull_request',
    'create_pull_request_review'
  ));

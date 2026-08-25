create index review_jobs_delivery_id_idx on review_jobs (delivery_id);
create index review_jobs_pull_request_id_idx on review_jobs (pull_request_id);
create index code_chunks_pull_request_id_idx on code_chunks (pull_request_id);
create index model_calls_prompt_version_id_idx on model_calls (prompt_version_id);

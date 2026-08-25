alter table model_calls
  alter column cost_usd type numeric(18, 12) using cost_usd::numeric(18, 12),
  add column latency_ms integer not null default 0,
  add constraint model_calls_latency_ms_non_negative check (latency_ms >= 0);

alter table agent_events
  add column sequence bigserial,
  add constraint agent_events_sequence_unique unique (sequence);

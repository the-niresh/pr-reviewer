-- Task 15: operator-declared notification channels. Confidentiality is a
-- declared enum, never inferred from transport. Default is restricted: an unset
-- value must not become ordinary. The webhook URL stays on the runner; this
-- table stores only a sha256 of the endpoint. HOSTED_EXEMPTIONS stays empty;
-- new text columns are allowlisted in control_plane.boundary.

create table notification_channels (
  id uuid primary key default gen_random_uuid(),
  installation_id bigint not null references installations(id),
  name text not null,
  transport text not null check (transport in ('slack', 'telegram', 'discord')),
  confidentiality text not null default 'restricted'
    check (confidentiality in ('restricted', 'ordinary')),
  purpose text not null check (purpose in ('security_alert', 'review_ping')),
  endpoint_hash text not null check (endpoint_hash ~ '^[0-9a-f]{64}$'),
  revoked boolean not null default false,
  created_at timestamptz not null default now()
);

create index notification_channels_installation_idx
  on notification_channels (installation_id);

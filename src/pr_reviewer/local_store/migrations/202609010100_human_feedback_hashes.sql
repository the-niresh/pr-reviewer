-- Task 15: human feedback carries original and edited hashes and may record an
-- edit. Append-only: this migration does not add an UPDATE trigger that would
-- rewrite a prior row. Prompts are not stored here.

create table local_human_decisions_new (
  id integer primary key autoincrement,
  finding_id text not null references local_findings (id),
  decision text not null
    check (decision in ('approved', 'rejected', 'disputed', 'edited')),
  decided_by text not null,
  note text,
  original_hash text not null default '',
  edited_hash text not null default '',
  created_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

insert into local_human_decisions_new (
  id, finding_id, decision, decided_by, note, created_at
)
select id, finding_id, decision, decided_by, note, created_at
from local_human_decisions;

drop table local_human_decisions;

alter table local_human_decisions_new rename to local_human_decisions;

create index local_human_decisions_finding_idx
  on local_human_decisions (finding_id, created_at);

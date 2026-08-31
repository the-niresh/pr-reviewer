"""SQLite persistence for workflow step completion. Queue state stays off this table."""

from __future__ import annotations

import json
import sqlite3
from typing import Protocol

from pr_reviewer.workflow.engine import STEP_NAMES, WorkflowInput, WorkflowState


class WorkflowStore(Protocol):
    def ensure_run(self, workflow_id: str, inp: WorkflowInput) -> None: ...
    def load_input(self, workflow_id: str) -> WorkflowInput: ...
    def completed_outputs(self, workflow_id: str) -> dict[str, object]: ...
    def mark_step_completed(self, workflow_id: str, step_name: str, output: object) -> None: ...
    def set_outcome(self, workflow_id: str, outcome: str, reason: str | None) -> None: ...
    def get_state(self, workflow_id: str) -> WorkflowState: ...


class SqliteWorkflowStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def ensure_run(self, workflow_id: str, inp: WorkflowInput) -> None:
        self._connection.execute(
            """
            insert or ignore into workflow_runs (
              workflow_id, job_id, head_sha, trace_id, lease_token, input_json
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                inp.job_id,
                inp.head_sha,
                inp.trace_id,
                inp.lease_token,
                json.dumps(
                    {
                        "job_id": inp.job_id,
                        "head_sha": inp.head_sha,
                        "trace_id": inp.trace_id,
                        "lease_token": inp.lease_token,
                    }
                ),
            ),
        )
        self._connection.commit()

    def load_input(self, workflow_id: str) -> WorkflowInput:
        row = self._connection.execute(
            "select input_json from workflow_runs where workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"no workflow run {workflow_id}")
        payload = json.loads(str(row["input_json"]))
        return WorkflowInput(
            job_id=str(payload["job_id"]),
            head_sha=str(payload["head_sha"]),
            trace_id=str(payload["trace_id"]),
            lease_token=str(payload.get("lease_token", "")),
        )

    def completed_outputs(self, workflow_id: str) -> dict[str, object]:
        rows = self._connection.execute(
            """
            select step_name, output_json from workflow_steps
            where workflow_id = ? order by completed_at, step_name
            """,
            (workflow_id,),
        ).fetchall()
        return {str(row["step_name"]): json.loads(str(row["output_json"])) for row in rows}

    def mark_step_completed(self, workflow_id: str, step_name: str, output: object) -> None:
        self._connection.execute(
            """
            insert or ignore into workflow_steps (workflow_id, step_name, output_json)
            values (?, ?, ?)
            """,
            (workflow_id, step_name, json.dumps(output)),
        )
        self._connection.commit()

    def set_outcome(self, workflow_id: str, outcome: str, reason: str | None) -> None:
        self._connection.execute(
            """
            update workflow_runs
            set outcome = ?, reason = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            where workflow_id = ?
            """,
            (outcome, reason, workflow_id),
        )
        self._connection.commit()

    def get_state(self, workflow_id: str) -> WorkflowState:
        row = self._connection.execute(
            "select outcome, reason from workflow_runs where workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"no workflow run {workflow_id}")
        outputs = self.completed_outputs(workflow_id)
        return WorkflowState(
            workflow_id=workflow_id,
            completed_steps=tuple(name for name in STEP_NAMES if name in outputs),
            outcome=None if row["outcome"] is None else str(row["outcome"]),
            reason=None if row["reason"] is None else str(row["reason"]),
        )

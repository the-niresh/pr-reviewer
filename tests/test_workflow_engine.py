"""Failing tests for the simple Python workflow engine (master Task 16).

Review_jobs stays queue state. Step completion lives in a local table. Routing and
events are injected callables, the same way retrieval takes record_selection: gates/
does not exist on this branch, and a hosted event writer would pull Neon into the
runner. Imports of new modules stay inside test bodies.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pr_reviewer.contracts.runner import LeaseState

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "pr_reviewer"
STEPS = (
    "fetch",
    "baseline_review",
    "retrieval",
    "verification",
    "routing",
    "storage",
)
HEAD_SHA = "a" * 40
OTHER_SHA = "b" * 40
ENGINES = ("simple", "langgraph")


class SimulatedCrash(Exception):
    """Raised by a step handler to stand in for a process crash mid-pipeline."""


def _input(**overrides: str) -> Any:
    from pr_reviewer.workflow.engine import WorkflowInput

    fields = {
        "job_id": "job-1",
        "head_sha": HEAD_SHA,
        "trace_id": "trace-1",
        "lease_token": "lease-1",
    }
    fields.update(overrides)
    return WorkflowInput(**fields)


def _store(tmp_path: Path) -> Any:
    from pr_reviewer.local_store.sqlite import open_local_store
    from pr_reviewer.workflow.store import SqliteWorkflowStore

    local = open_local_store(tmp_path / "local_state.sqlite3")
    return SqliteWorkflowStore(local.connection)


def _counting_handlers(
    counts: dict[str, int],
    *,
    crash_before: str | None = None,
    crashed: dict[str, bool] | None = None,
) -> dict[str, Callable[..., object]]:
    crashed = crashed if crashed is not None else {"done": False}

    def make(name: str) -> Callable[..., object]:
        def handler(_inp: Any, _outputs: dict[str, object]) -> object:
            if name == crash_before and not crashed["done"]:
                crashed["done"] = True
                raise SimulatedCrash(name)
            counts[name] = counts.get(name, 0) + 1
            if name == "baseline_review":
                counts["model_calls"] = counts.get("model_calls", 0) + 1
            if name == "storage":
                counts["posts"] = counts.get("posts", 0) + 1
                counts["notifies"] = counts.get("notifies", 0) + 1
            return name

        return handler

    return {name: make(name) for name in STEPS}


def _engine(
    tmp_path: Path,
    *,
    engine_cls: str = "simple",
    handlers: dict[str, Callable[..., object]] | None = None,
    counts: dict[str, int] | None = None,
    heartbeat: Callable[[Any], LeaseState] | None = None,
    current_head_sha: Callable[[Any], str] | None = None,
    record_event: Callable[[str, str, dict[str, str | int]], None] | None = None,
    step_timeouts: dict[str, float] | None = None,
    crash_before: str | None = None,
    crashed: dict[str, bool] | None = None,
) -> Any:
    if engine_cls == "langgraph":
        from pr_reviewer.workflow.langgraph_engine import LangGraphEngine

        cls: Any = LangGraphEngine
    else:
        from pr_reviewer.workflow.simple_engine import SimpleEngine

        cls = SimpleEngine

    if handlers is None:
        counts = counts if counts is not None else {}
        handlers = _counting_handlers(counts, crash_before=crash_before, crashed=crashed)
    return cls(
        store=_store(tmp_path),
        fetch=handlers["fetch"],
        baseline_review=handlers["baseline_review"],
        retrieval=handlers["retrieval"],
        verification=handlers["verification"],
        routing=handlers["routing"],
        storage=handlers["storage"],
        heartbeat=heartbeat,
        current_head_sha=current_head_sha,
        record_event=record_event,
        step_timeouts=step_timeouts,
    )


@pytest.mark.parametrize("engine_cls", ENGINES)
def test_run_executes_all_six_steps_once(tmp_path: Path, engine_cls: str) -> None:
    counts: dict[str, int] = {}
    engine = _engine(tmp_path, engine_cls=engine_cls, counts=counts)
    result = engine.run("wf-1", _input())
    assert result.status == "completed"
    assert [counts[name] for name in STEPS] == [1] * 6
    assert counts["model_calls"] == 1
    assert counts["posts"] == 1
    assert counts["notifies"] == 1


@pytest.mark.parametrize("engine_cls", ENGINES)
def test_get_state_lists_completed_steps_without_a_running_queue_status(
    tmp_path: Path,
    engine_cls: str,
) -> None:
    engine = _engine(tmp_path, engine_cls=engine_cls)
    engine.run("wf-1", _input())
    state = engine.get_state("wf-1")
    assert state.completed_steps == STEPS
    assert state.outcome == "completed"
    assert not hasattr(state, "status") or state.outcome != "running"


@pytest.mark.parametrize("engine_cls", ENGINES)
@pytest.mark.parametrize("crash_before", STEPS)
def test_resume_after_crash_before_each_step_does_not_repeat_completed_effects(
    tmp_path: Path, crash_before: str, engine_cls: str
) -> None:
    counts: dict[str, int] = {}
    crashed = {"done": False}
    engine = _engine(
        tmp_path,
        engine_cls=engine_cls,
        counts=counts,
        crash_before=crash_before,
        crashed=crashed,
    )
    with pytest.raises(SimulatedCrash):
        engine.run("wf-1", _input())

    crashed_index = STEPS.index(crash_before)
    for name in STEPS[:crashed_index]:
        assert counts[name] == 1, name
    for name in STEPS[crashed_index:]:
        assert counts.get(name, 0) == 0, name
    if crashed_index > STEPS.index("baseline_review"):
        assert counts["model_calls"] == 1
    else:
        assert counts.get("model_calls", 0) == 0

    resumed = engine.resume("wf-1")
    assert resumed.status == "completed"
    assert [counts[name] for name in STEPS] == [1] * 6
    assert counts["model_calls"] == 1
    assert counts["posts"] == 1
    assert counts["notifies"] == 1


@pytest.mark.parametrize("engine_cls", ENGINES)
def test_rerunning_a_completed_workflow_is_a_no_op_for_external_effects(
    tmp_path: Path, engine_cls: str
) -> None:
    counts: dict[str, int] = {}
    engine = _engine(tmp_path, engine_cls=engine_cls, counts=counts)
    engine.run("wf-1", _input())
    again = engine.run("wf-1", _input())
    assert again.status == "completed"
    assert counts["model_calls"] == 1
    assert counts["posts"] == 1
    assert counts["notifies"] == 1


@pytest.mark.parametrize("engine_cls", ENGINES)
def test_cancelled_lease_between_steps_records_cancelled_not_a_dead_lease(
    tmp_path: Path,
    engine_cls: str,
) -> None:
    counts: dict[str, int] = {}
    events: list[tuple[str, dict[str, str | int]]] = []
    heartbeats = iter(
        [
            LeaseState(status="active"),
            LeaseState(status="cancelled"),
        ]
    )

    def heartbeat(_inp: Any) -> LeaseState:
        return next(heartbeats)

    def record_event(_job_id: str, event_type: str, payload: dict[str, str | int]) -> None:
        events.append((event_type, payload))

    engine = _engine(
        tmp_path,
        engine_cls=engine_cls,
        counts=counts,
        heartbeat=heartbeat,
        record_event=record_event,
    )
    result = engine.run("wf-1", _input())
    assert result.status == "cancelled"
    assert result.reason == "cancelled"
    assert counts.get("fetch", 0) == 1
    assert counts.get("baseline_review", 0) == 0
    assert counts.get("model_calls", 0) == 0
    reasons = [payload.get("reason") for _type, payload in events]
    assert "cancelled" in reasons
    assert "invalid_or_expired" not in reasons


@pytest.mark.parametrize("engine_cls", ENGINES)
def test_invalid_or_expired_lease_is_not_recorded_as_cancelled(
    tmp_path: Path, engine_cls: str
) -> None:
    heartbeats = iter([LeaseState(status="active"), LeaseState(status="invalid_or_expired")])
    engine = _engine(
        tmp_path, engine_cls=engine_cls, heartbeat=lambda _inp: next(heartbeats)
    )
    result = engine.run("wf-1", _input())
    assert result.reason == "invalid_or_expired"
    assert result.status != "cancelled" or result.reason != "cancelled"


@pytest.mark.parametrize("engine_cls", ENGINES)
def test_superseded_head_sha_cancels_before_the_next_step(
    tmp_path: Path, engine_cls: str
) -> None:
    counts: dict[str, int] = {}
    shas = iter([HEAD_SHA, OTHER_SHA])
    engine = _engine(
        tmp_path,
        engine_cls=engine_cls,
        counts=counts,
        current_head_sha=lambda _inp: next(shas),
    )
    result = engine.run("wf-1", _input())
    assert result.status == "cancelled"
    assert result.reason == "superseded"
    assert counts.get("fetch", 0) == 1
    assert counts.get("baseline_review", 0) == 0
    assert counts.get("model_calls", 0) == 0


@pytest.mark.parametrize("engine_cls", ENGINES)
def test_every_step_transition_records_a_flat_event(
    tmp_path: Path, engine_cls: str
) -> None:
    events: list[tuple[str, dict[str, str | int]]] = []

    def record_event(_job_id: str, event_type: str, payload: dict[str, str | int]) -> None:
        events.append((event_type, payload))
        for value in payload.values():
            assert not isinstance(value, (dict, list))

    engine = _engine(tmp_path, engine_cls=engine_cls, record_event=record_event)
    engine.run("wf-1", _input())
    completed = [
        payload["step"] for event_type, payload in events if event_type.endswith("completed")
    ]
    assert tuple(completed) == STEPS


def test_wait_for_artifact_times_out_loudly(tmp_path: Path) -> None:
    from pr_reviewer.workflow.simple_engine import wait_for_artifact

    missing = tmp_path / "never-created"
    with pytest.raises(RuntimeError, match="TIMEOUT"):
        wait_for_artifact(missing, deadline_seconds=0.05)


def test_node_deadline_expires_when_a_step_waits_on_a_missing_artifact(tmp_path: Path) -> None:
    from pr_reviewer.workflow.simple_engine import wait_for_artifact

    missing = tmp_path / "never-created"

    def fetch(_inp: Any, _outputs: dict[str, object]) -> object:
        wait_for_artifact(missing, deadline_seconds=0.05)
        return "fetched"

    handlers = _counting_handlers({})
    handlers["fetch"] = fetch
    engine = _engine(
        tmp_path, engine_cls="simple", handlers=handlers, step_timeouts={"fetch": 0.05}
    )
    with pytest.raises(RuntimeError, match="TIMEOUT"):
        engine.run("wf-1", _input())


def test_workflow_outcome_rejects_queue_running_status(tmp_path: Path) -> None:
    import sqlite3

    from pr_reviewer.local_store.sqlite import open_local_store

    local = open_local_store(tmp_path / "local_state.sqlite3")
    with pytest.raises(sqlite3.IntegrityError):
        local.connection.execute(
            "insert into workflow_runs "
            "(workflow_id, job_id, head_sha, trace_id, input_json, outcome) "
            "values ('wf-1', 'job-1', ?, 'trace-1', '{}', 'running')",
            (HEAD_SHA,),
        )
        local.connection.commit()


def test_hosted_schema_has_no_workflow_tables() -> None:
    from pr_reviewer.db.client import connection

    with connection() as conn:
        rows = conn.execute(
            """
            select table_name from information_schema.tables
            where table_schema = 'public' and table_name like 'workflow%'
            """
        ).fetchall()
    names = sorted(str(row["table_name"]) for row in rows)
    assert names == []


def test_workflow_package_does_not_import_langgraph_gates_events_jobs_or_db() -> None:
    forbidden = (
        "langgraph",
        "pr_reviewer.gates",
        "pr_reviewer.events",
        "pr_reviewer.jobs",
        "pr_reviewer.db",
        "pr_reviewer.control_plane",
    )
    root = SRC_ROOT / "workflow"
    assert root.is_dir()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        text = path.read_text(encoding="utf-8")
        adapter_only = path.name == "langgraph_engine.py"
        for token in forbidden:
            if token == "langgraph" and adapter_only:
                continue
            if token == "langgraph":
                assert token not in text.lower()
            else:
                assert token not in text
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if adapter_only and alias.name.startswith("langgraph"):
                        continue
                    assert not alias.name.startswith("langgraph")
            if isinstance(node, ast.ImportFrom) and node.module:
                if not (adapter_only and node.module.startswith("langgraph")):
                    assert not node.module.startswith("langgraph")
                assert not node.module.startswith("pr_reviewer.gates")
                assert not node.module.startswith("pr_reviewer.events")
                assert not node.module.startswith("pr_reviewer.jobs")
                assert not node.module.startswith("pr_reviewer.db")


def test_simple_engine_defines_routing_as_an_injected_callable() -> None:
    source = (SRC_ROOT / "workflow" / "simple_engine.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "route_finding" not in source
    assert "pr_reviewer.gates" not in source
    assigned = {node.arg for node in ast.walk(tree) if isinstance(node, ast.arg)}
    assert "routing" in assigned

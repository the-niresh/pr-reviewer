# Phase 10 - ✅ Tooling and Sandboxing

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ✅ SANDBOX PROOF GATE REPRODUCED 2026-09-01.** Master Task 14 is ✅. Master Task 23
is still marked ⬜ in the master plan; treated as done because `7669ec6` shipped it.
Product-runtime Tasks 6 and 7 are ✅. Product-runtime Task 10 stays ⬜. That is the hosted
end-to-end, not this sandbox gate.

## 1 - ✅ The model names an ID, not a command

`SandboxJob` (`verification/docker_sandbox.py:44`) is frozen with `extra=forbid`. A
shell-string field is unconstructable. `DEFAULT_COMMANDS` maps IDs to argv tuples
(`verification/docker_sandbox.py:35`). An unknown ID is rejected and never run
(`tests/test_docker_sandbox.py`).

## 2 - ✅ SandboxSpec cannot relax isolation

`SandboxSpec` (`containers/runtime.py:69`) holds image digest, argv, work directory,
and resource ceilings. There is no field for network, user, capabilities, or the
Docker socket. A string `command` raises `TypeError`. An image without `@sha256:`
raises `ValueError`. `DockerRuntime.run` (`containers/docker.py:285`) always passes
`--network none`, `--read-only`, `--cap-drop ALL`, and never mounts the Docker
socket (`containers/docker.py:20`).

## 3 - ✅ Missing Docker never falls back to the host

If the probe is not `full_mode_ready`, verification returns inconclusive and routes
to a person (`verification/docker_sandbox.py:106`). `select_runtime_mode`
(`runner/modes.py:51`) grants `analysis_only` when Docker is not ready. There is no
host-execution path. `test_missing_docker_returns_inconclusive_and_never_runs_the_command_on_the_host`
and `test_run_never_executes_spec_command_on_the_host_when_docker_is_missing` pin
that.

## 4 - ✅ Probe is proof, not PATH

`ContainerProbe.full_mode_ready` is true only when CLI, daemon, socket, pull,
non-root, network isolation, limits, and platform all pass
(`containers/runtime.py:60`). `reviewer doctor` shows disabled features before
asking to confirm analysis-only (`tests/test_doctor_docker.py`). It never offers to
install Docker.

## 5 - ✅ Static checks do not execute PR code

File existence and changed-line membership run against the snapshot, not a
container (`tests/test_static_checks.py`). A stale head SHA is inconclusive. Blank
evidence fails.

## Design gate - ✅

✅ Untrusted PR code runs in Docker or not at all. Missing Docker is analysis-only.
Isolation flags are not caller-configurable.

## Test gate - ✅ reproduced

The proof gate is: malicious fixtures cannot access host files, Docker socket,
metadata services, secrets, or unrestricted network. Missing Docker never falls
back to host execution.

Command, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_dashboard_auth.py::test_unauthenticated_docs_and_unknown_paths_are_not_ok tests/test_docker_sandbox.py tests/test_container_runtime.py tests/test_doctor_docker.py tests/test_static_checks.py tests/test_runner_modes.py
............................................................             [100%]
60 passed, 1 warning in 29.07s
```

`test_run_argv_has_isolation_flags_limits_and_no_docker_socket` is the isolation
argv proof. `test_real_sandbox_is_isolated_and_uses_a_temporary_work_directory`
runs a real container. `test_unauthenticated_docs_and_unknown_paths_are_not_ok`
is the 06:11 FIX.

⚠️ This is not the hosted end-to-end at `https://reviewer.niresh.tech`. Runtime
Task 10 stays morning work.

## Settled - ✅

- ✅ Docker is the only v1 `ContainerRuntime`. There is no host runner.
- ✅ `HOSTED_EXEMPTIONS` stays empty.

## Open Decisions - ❓

- ❓ None for this sandbox gate. Public deploy remains runtime Task 10.

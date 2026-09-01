# Phase 18 - ✅ Developer Experience

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ✅ LOCAL INSTALL-PAIR-DIAGNOSE-START-UPDATE-ROLLBACK-UNINSTALL PROOF
REPRODUCED 2026-09-01.** Master Tasks 10, 20 through 23, and 25 are treated as
done at HEAD. Product-runtime Tasks 5, 8, and 9 are ✅. Master Task 26 stays ⬜
and is not this local DX gate. This is not a public GitHub release URL and not
the hosted end-to-end at reviewer.niresh.tech.

## 1 - ✅ The `reviewer` CLI is a thin router

`reviewer_entry.main` (`reviewer_entry.py:23`) lazy-imports each subcommand after
the name is known. Usage lists `setup|doctor|trace|start|stop|status|open|update|uninstall`
(`reviewer_entry.py:20`). `doctor` loads `runner.cli.doctor`, not `cli.doctor`.
`setup` is the operator wizard. `update` and `uninstall` go through `runner.cli`,
not the operator CLI (`tests/test_runner_uninstall.py`). An unknown subcommand is
nonzero (`tests/test_doctor_docker.py`).

## 2 - ✅ Install verifies a checksum and needs no administrator rights

`scripts/install.sh` copies the archive, runs `sha256sum -c`, then copies into
`--prefix` (`scripts/install.sh:39`). There are no secret flags
(`tests/test_installer.py:109`). A bad digest is rejected
(`tests/test_installer.py:60`). `test_install_runs_in_clean_linux_container`
runs that script as uid 65532 in pinned busybox. `install_user_service`
(`runner/cli/service.py:47`) writes under the home directory.
`_refuse_system_path` (`runner/cli/service.py:236`) refuses `/etc/` and
LaunchDaemons.

## 3 - ✅ Setup and doctor do not print or accept hosted secrets

`run_setup` (`cli/main.py:21`) stores the model key from hidden input, not argv
(`tests/test_installer.py:18`). Secret-bearing flags exit
(`cli/main.py:32`). The origin must be `https://` (`cli/main.py:38`).
`run_doctor` (`cli/doctor.py:27`) reports control-plane reachability, pairing,
model-key presence, port, disk, and Docker mode (`tests/test_doctor.py`).
Doctor and setup never prompt for hosted secrets. Missing Docker does not
auto-install Docker (`tests/test_doctor_docker.py`).

## 4 - ✅ Pair, start, status, and stop stay on loopback

Pairing stores a hash, not the plaintext code (`tests/test_runner_pairing.py`).
Exchange returns a working credential once. Replay is denied. `start_local_onboarding`
(`runner/cli/service.py:90`) refuses any host other than `127.0.0.1`
(`runner/cli/service.py:102`). Status is not running when the local port is
closed (`tests/test_user_service.py`). `open` prints the URL when no browser
exists.

## 5 - ✅ Update checks the digest and keeps a prior copy for rollback

`apply_update` (`runner/update.py:25`) hashes the artifact before replace
(`runner/update.py:33`). A mismatch raises `UpdateError` and leaves the
installed bytes unchanged (`tests/test_runner_update.py:21`). A successful
replace keeps `{name}.prior` (`runner/update.py:40`). A failed replace writes
the prior bytes back (`runner/update.py:50`).

## 6 - ✅ Uninstall preserves data unless delete is confirmed

`uninstall_runner` (`runner/cli/uninstall.py:34`) returns after stopping the
vector store when `preserve_data` is true. Deleting without `confirm_delete`
raises `UninstallError` (`runner/cli/uninstall.py:42`). Secrets and SQLite go
only on the confirmed path (`tests/test_runner_uninstall.py`).

## 7 - ✅ Trace export redacts, and prompt versions are inspectable

`reviewer trace --json` redacts secret-like keys
(`tests/test_trace_cli.py:237`). `reconstruct_trace`
(`observability/trace.py:171`) strips keys that look like secrets
(`observability/trace.py:288`). `PromptRegistry.register`
(`prompts/registry.py:27`) rejects an update to an existing name and version
(`tests/test_prompt_registry.py`).

## Design gate - ✅

✅ A clean supported test machine can install a checksummed asset without
elevation, pair, diagnose, start on loopback, update with rollback, and
uninstall without secret output.

## Test gate - ✅ reproduced

The proof gate is: a clean supported machine can install, pair, diagnose,
start, update, roll back, and uninstall from versioned assets without
administrator rights or secret output.

Command, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_dashboard_auth.py::test_unauthenticated_docs_and_unknown_paths_are_not_ok tests/test_installer.py tests/test_doctor.py tests/test_doctor_docker.py tests/test_user_service.py tests/test_runner_update.py tests/test_runner_uninstall.py tests/test_runner_pairing.py tests/test_trace_cli.py::test_cli_json_export_redacts_secret_like_keys_and_shapes_segments tests/test_prompt_registry.py
.....................................................................    [100%]
69 passed, 1 warning in 15.24s
```

`test_install_runs_in_clean_linux_container` is the non-root checksummed install.
`test_update_keeps_the_prior_version_for_rollback` is the rollback.
`test_setup_rejects_secret_bearing_flags` and
`test_cli_json_export_redacts_secret_like_keys_and_shapes_segments` are the
no-secret-output proof. `test_unauthenticated_docs_and_unknown_paths_are_not_ok`
is the 06:11 FIX.

⚠️ This is not a public GitHub Releases URL. Task 26 (hiring README) is not
this gate. Runtime Task 10 is not this gate. This document invents no eval
number.

## Settled - ✅

- ✅ Install and update verify sha256 before replacing files.
- ✅ User units live under the home directory. A system path is refused.
- ✅ Setup takes the model key from hidden input. Hosted secret flags are
  rejected.
- ✅ Uninstall preserves local reviews and volumes by default.

## Open Decisions - ❓

- ❓ Which operating systems ship in v1: Linux only, or Linux and macOS.
- ❓ Which public versioned asset URL the morning install proof will use once
  a release is published.

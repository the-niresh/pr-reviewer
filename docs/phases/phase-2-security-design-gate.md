# Phase 2 - ⚠️ Security and Trust Boundaries

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ⚠️ TEST GATE PARTIAL 2026-09-01.** Design gate approved 2026-08-27. The unit proof
gate listed below was reproduced on this checkout. Product-runtime Task 10 is still ⬜, so
the hosted end-to-end half of this phase stays open.

## 1 - ✅ Assets, ranked by what a breach costs

| # | Asset | Held by | If it leaks |
|---|---|---|---|
| A1 | **GitHub App private key** | control plane only | catastrophic and cross-tenant. One key acts as the app on **every** installation. This is the crown jewel and the reason it never leaves the hosted plane. |
| A2 | Webhook secret | control plane only | attacker forges deliveries, creates jobs, burns budget |
| A3 | Neon credentials | control plane only | all tenants' identity and job metadata |
| A4 | User's private source | runner only, never hosted | someone else's intellectual property, and your worst headline |
| A5 | User's model API key | runner only, OS keyring | direct financial loss, impersonation |
| A6 | Runner credential | runner (hashed in Neon) | claim that runner's jobs, obtain its repo-scoped tokens |
| A7 | Installation token | in memory only, minutes | repo read plus PR write while valid |
| A8 | Notification secrets | runner only, OS keyring | send as you, or read a restricted channel |
| A9 | Undisclosed security findings | runner, then restricted channel | an unpatched exploit, handed to whoever reads it |
| A10 | Eval ground truth | local | poisoned labels silently degrade the product |

## 2 - ✅ Attackers

| # | Attacker | Can do | Wants |
|---|---|---|---|
| T1 | **Malicious PR author** | write anything into a diff, filename, branch name, commit message, PR title or body. Cannot authenticate. | prompt injection: make the agent leak, execute, or post on their behalf |
| T2 | **Malicious repository owner** | installs the app, controls the whole repo including the default branch and its instruction files | escape tenancy, reach another tenant, abuse the hosted service |
| T3 | Network attacker | observe, attempt MITM and replay | tokens, pairing codes |
| T4 | Compromised dependency | run code in either plane | anything |
| T5 | Local process on the user's machine | reach the loopback UI, read files as that user | model keys, findings, the local API |
| T6 | **Compromised control plane** | full read of hosted state | see section 4 |
| T7 | Operator, meaning you | full hosted access by design | see section 4 |

⚠️ T1 is the attacker most systems forget, because it does not need an account. Anyone who can open a
pull request against a public repository is already inside the input path.

## 3 - ✅ Threats per boundary

Boundaries B1 to B4 are defined in the Phase 1 record.

| Boundary | Attacker | Threat | Control |
|---|---|---|---|
| B1 internet → control plane | T1, T3 | forged webhook | HMAC verified **before** parsing; reject if the secret is unset rather than skip |
| B1 | T3 | replayed delivery | dedupe on `X-GitHub-Delivery`, durable |
| B1 | T3 | stolen pairing code | one-use, 10 minute expiry, stored hashed, PKCE verifier |
| B1 | T2, T3 | credential stuffing on runner auth | credentials are random and hashed; revocation is immediate |
| B2 control plane → runner | T6 | job envelope carries a command | envelope is typed identifiers and policy only, unknown fields rejected |
| B2 | T2 | token issued to the wrong runner | broker checks lease owner, repository, and head SHA before issuing |
| B2 | T2, T5 | token reused after the job | repo-scoped, minutes-long, memory only, discarded on completion or lease loss |
| B3 runner → control plane | T5 | private data smuggled in a result | acknowledgement is a closed typed shape: terminal state, error class, aggregate counts, hash |
| B3 | T5 | private data in an error string | error **class**, never an error message |
| B4 untrusted text → prompt | **T1** | injection from a diff | every repository string passes `wrap_untrusted`; canary test forbids raw interpolation |
| B4 | **T2** | injection from an instruction file | default branch only, at a resolved SHA, allowlisted names, size-capped, off by default |
| B4 | T1, T2 | injection escalating to an action | the model emits `FindingCandidate` only; system code owns id, verification, public safety, status and posting |
| B4 | T1 | injection reaching a shell | sandbox takes a typed spec with allowlisted command IDs. No model-supplied string is ever executed |
| build and release | **T4** | compromised dependency or base image | lockfiles checked in CI, dependency and container scanning, images pinned by digest, non-root, SBOM and checksums on release assets (master Task 23) |
| build and release | **T4** | malicious install script | versioned release assets with published checksums. ⚠️ Never pipe a mutable `main` script into a shell (master Task 25) |
| B2, tenancy | **T2** | cross-installation data access | every lookup scoped by numeric installation and repository ID, see section 6 |
| B2, tenancy | **T2** | ⚠️ **denial reason as an oracle**: distinguishing "not yours" from "does not exist" reveals another tenant's data | a denial reason must be computable from data the caller is already authorised to see. Collapse the two into one indistinguishable reason |

⚠️ Telling the model to ignore instructions in the diff is **not** a control. Every defence above is
structural: the model is never given a field or a code path that could carry the attack forward.

## 4 - ✅ Assume breach

The point of the two-plane split is that it survives this question.

**If the control plane is fully compromised (T6, or a malicious operator T7):** the attacker gets
identity records, repository IDs, job state, redacted lifecycle events, aggregate token and cost
numbers, and runner credential **hashes**. They also get A1, A2 and A3, which is severe and means
every installation must be treated as compromised and the App key rotated.

They do **not** get: source, diffs, findings, rationale, sandbox logs, embeddings, or any model key.
Those never exist on that machine. ✅ That is the property the architecture buys, and it is what makes
"we host a code review service" defensible at all.

**If a runner is compromised (T5):** the attacker gets that one user's source, model keys, findings and
notification secrets, plus the ability to act as that runner. They do **not** get the App private key,
the webhook secret, Neon credentials, or any other tenant's anything. Blast radius is one user.

## 5 - ✅ GitHub App permissions, least privilege

| Permission | Level | Why | If omitted |
|---|---|---|---|
| Metadata | Read | mandatory for any App | nothing works |
| Pull requests | Read and Write | read the PR, post one review with comments | cannot post, review-only |
| Contents | Read | fetch patches, clone fallback, read default-branch instruction files, index for retrieval | no fallback, no retrieval, no instruction files |
| Checks | Read | only if CI-gating is enabled | CI-gating unavailable, and it is off by default |
| Issues | Read | linked-issue context for the description check | slightly weaker step 1 |
| Administration, Members, Actions, Secrets, Packages, Deployments | ❌ none | never needed | n/a |

**Events subscribed:** `pull_request` only. Add `check_suite` only for repositories that enable
CI-gating.

⚠️ **Contents: Read is repository-wide, not PR-scoped.** GitHub has no narrower grant. That is an
honest privacy cost and it must be stated in onboarding, because full-mode retrieval reads and indexes
the whole default branch, not only the changed files.

## 6 - ✅ Tenant isolation

This section exists for **T2**, the malicious repository owner. Everything here assumes a paying,
authenticated user is trying to reach another tenant.

- ✅ Every lookup is scoped by **numeric** `installation_id` and `repository_id`.
- ⚠️ Repository names are labels. A rename must never move, orphan, or expose data.
- ✅ One active runner assignment per repository in v1.
- ✅ A lease binds runner, installation, repository, PR number and head SHA together. All five, not a
  subset.
- ✅ The token broker re-checks the lease at issue time, not at claim time.
- ✅ Revoking an installation or a runner stops new work immediately, and the runner discards any token
  it holds.
- ✅ ⚠️ **A denial reason is part of the tenancy boundary.** It must be computable from data the caller
  is already authorised to see. If telling the two cases apart requires a query the caller could not
  make, the two cases must return the **same** reason. "Not registered under your installation" and
  "not registered anywhere" are one reason, not two.
- ✅ No authorization query may be unscoped. A lookup filtered only by `github_repository_id`, with no
  `installation_id`, is a cross-tenant read even when its result is discarded.

⚠️ Found while implementing runtime Task 1. The first implementation distinguished the two cases and
added an unscoped `select 1 from repositories where github_repository_id = %s` to do it. Two tests
disagreed about the expected reason, which read as a contradiction; it was actually the tests
describing a property the implementation had not yet met. Indistinguishability was the answer.

## 7 - ✅ Secret lifecycle

| Secret | Stored | Rotation | Revocation | Never |
|---|---|---|---|---|
| App private key | control plane secret manager | manual, documented | regenerate in GitHub | in a repo, image, log, or client |
| Webhook secret | control plane secret manager | manual | rotate in GitHub, redeploy | in a client |
| Neon credentials | control plane environment | provider rotation | provider | in a client |
| Runner credential | OS keyring on the runner, hash in Neon | `rotate_runner_credential` | immediate, server side | in SQLite, plaintext anywhere |
| Model API key | OS keyring, mode `0600` file as documented fallback | user replaces | user deletes | in argv, shell history, env of the daemon, logs, hosted plane |
| Installation token | process memory | expires in minutes | discard on completion or lease loss | on disk, in Neon |
| Notification secrets | OS keyring on the runner | user replaces | user deletes | hosted plane |

⚠️ **Model keys are read from the keyring at call time, not held in `os.environ`.** A subprocess or a
container escape inherits the environment. It does not inherit a keyring lookup.

## 8 - ✅ Public security disclosure policy

- ✅ Critical and high security findings **never** post publicly. This survives the auto-post gate.
- ✅ They route to a channel declared `restricted`, plus the local approval queue.
- ✅ A public comment on a security finding is possible only after human approval, and carries a
  summary with no reproduction detail.
- ✅ Restricted notification **titles** carry no finding detail, because a push preview renders on a
  locked screen.
- ⚠️ A private repository is not a safe audience. A contractor with repo access should not
  automatically learn about an unpatched auth bypass. Confidentiality is about who can read the
  channel, never about whether the repo is public.

## 9 - ✅ Sandbox threat model

**Adversary:** **T1**, pull request code, executing.
**Goals:** read host files, steal secrets, reach the network, escape to the host, persist, or exhaust
resources.

| Control | Stops |
|---|---|
| no network | exfiltration, callbacks, dependency fetch at run time |
| no host mounts except one scoped work directory | reading the user's files |
| no Docker socket | ⚠️ that mount is root on the host, full stop |
| non-root user, read-only root filesystem | persistence, tampering |
| dropped capabilities, default seccomp | kernel surface |
| CPU, memory, pids, disk, output and wall-clock limits | resource exhaustion, fork bombs, log flooding |
| image pinned by digest | a mutable tag changing underneath you |
| cleanup on every exit path, crash included | leftover state between jobs |
| typed spec, allowlisted command IDs | ⚠️ a model-supplied shell string, which is never executed |

✅ **Assumed:** container escape is possible in principle. The mitigation is that nothing valuable is
reachable from the host side. Secrets live in the keyring rather than the environment, and the work
directory holds only the checkout.

⚠️ Docker being installed and running is not proof that isolation works. `reviewer doctor` must verify
each control above, and full mode is unavailable until every check passes.

## Design gate - ✅ Approved

✅ Sections 1 through 9 approved by the owner on 2026-08-27. Every asset in section 1 has at least one named control, every
attacker in section 2 has at least one boundary that stops them, and no secret in section 7 crosses a
boundary Phase 1 did not declare.

## Test gate - ⚠️ partial, unit suite reproduced

The proof gate is: HMAC, tenant isolation, repository scope, secret canaries, token expiry,
runner revocation, unsafe finding routing, and host-execution denial all have
failing-then-passing tests.

Command, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_github_signature.py tests/test_webhook.py tests/test_control_plane_identity.py tests/test_prompt_boundaries.py tests/test_token_broker.py tests/test_runner_offline.py tests/test_notification_policy.py tests/test_docker_sandbox.py tests/test_doctor_docker.py tests/test_dashboard_auth.py
........................................................................ [ 60%]
...............................................                          [100%]
119 passed, 1 warning in 38.27s
```

What that suite proves, with the code it cites:

- HMAC before parse: `verify_github_signature` (`github/verify_signature.py:11`) runs in
  `github_webhook` (`control_plane/app.py:53`) before `request.json()`.
- Delivery dedupe: a replayed `X-GitHub-Delivery` hits `on conflict do nothing` and returns
  `duplicate` (`jobs/enqueue_review_job.py:38`).
- Tenant isolation: `authorize_repository` (`control_plane/repository_policy.py:150`) scopes
  the repository lookup by `installation_id` and `github_repository_id` together. A denial
  reason is part of the tenancy boundary. Covered by
  `test_cross_installation_access_is_denied_for_a_repository_registered_elsewhere`.
- Secret canaries: untrusted markers live only in `security/prompt_boundaries.py`.
  `wrap_untrusted` (`security/prompt_boundaries.py:34`) is the only string exit from
  `UntrustedText`. Connector audit still matches a short canary such as `gho_leaked`
  (`connectors/audit.py:20`).
- Token expiry and scope: `issue_job_token` (`control_plane/token_broker.py:49`) reuses
  `invalid_or_expired` for a wrong, expired, superseded, or finished lease, then
  re-checks `authorize_repository`. Tokens are contents-read and pull_requests-read only
  (`control_plane/token_broker.py:38`).
- Runner revocation: `test_runner_revocation_is_a_timestamp_not_a_delete` and
  `test_revoked_runner_fails_authorization`. The daemon treats `revoked_runner` as a stop
  (`runner/daemon.py:127`).
- Unsafe finding routing: `route_finding` (`notifications/gate.py:36`) is system-owned.
  Critical and high security findings stay private.
- Injection cannot set a gated field: `UntrustedText.__str__` raises
  (`security/prompt_boundaries.py:18`). Prompt assembly must call `wrap_untrusted`.
- Host-execution denial: missing or unready Docker returns inconclusive and routes to a
  person (`verification/docker_sandbox.py:110`). `SandboxSpec` has no shell-string field
  (`containers/runtime.py:11`).
- Dashboard deny-by-default: `create_dashboard_app` passes `docs_url=None`,
  `redoc_url=None`, `openapi_url=None` (`web/dashboard_api.py:69`). The guard is
  `if not public and not session_is_valid(...)` (`web/dashboard_api.py:98`). An
  unauthenticated loopback GET of `/openapi.json` or `/missing` is not 200.

⚠️ Still open: product-runtime Task 10. That is the hosted end-to-end proof at
`https://reviewer.niresh.tech`. The subdomain is not live tonight. This file does not
claim that half.

Master Tasks 3, 6 through 8, 10, 10B, 13 through 15, 17, 18, 23, and 25, and
runtime Tasks 1, 1A, 2 through 6, 8, and 9 are treated as implemented at HEAD. Runtime
Task 10 stays ⬜.

## Settled - ✅

These three were listed as decisions in the first draft. On review they are applications of rules
already approved, not new calls, so they are applied rather than asked:

- ✅ `Contents: Read` is repository-wide because GitHub offers no PR-scoped grant. That is a fact, and
  disclosing it is an obligation, not a choice. Now stated at onboarding step 5 in the runtime plan.
- ✅ A private repository is not a safe audience. This follows from the already-approved rule that
  critical and high security findings always route privately. Repo visibility was never the test.
- ✅ Model keys are read from the keyring per call and never enter the daemon environment. The approved
  constraint already names the OS secret store as the home; loading it into `os.environ` at boot would
  defeat that store entirely. Now a security invariant and a test step in runtime Task 5.

## Open Decisions - ❓

- ❓ None for the unit proof. Runtime Task 10 remains the hosted end-to-end half and is
  morning work, not a design choice.

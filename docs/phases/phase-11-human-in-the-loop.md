# Phase 11 - ✅ Human-in-the-Loop

| Mark | Means |
|---|---|
| ⬜ | Not done yet. I tick it when it lands |
| ✅ | Done, or in scope and agreed |
| ❌ | Deliberately not doing this |
| ❓ | Open decision, waiting on me |
| ⚠️ | Known trap. Read before writing the code |

**Status - ✅ HITL PROOF GATE REPRODUCED 2026-09-01.** Master Tasks 15 and 17 are ✅. Master
Tasks 21 and 22 are still marked ⬜ in the master plan; treated as done because `e704cd7`
and `5a95d15` shipped them. Product-runtime Task 8 is ✅. Master Task 24 stays ⬜
(FoodSpector shadow). Product-runtime Task 10 stays ⬜. Neither is this routing gate.

## 1 - ✅ The model does not choose the destination

`route_finding` (`notifications/gate.py:36`) is system-owned. Public post requires
auto-post, public posting, verified, public-safe, not private, not high-sensitivity,
and not inconclusive (`notifications/gate.py:49`). Anything else queues for a
person.

## 2 - ✅ Security findings stay restricted

Critical or unsafe security findings route privately even when marked public-safe
(`tests/test_notification_policy.py`). Unset channel confidentiality is restricted,
not ordinary. Restricted content on an ordinary channel is refused, not
downgraded. The model cannot bypass routing through severity, confidence,
rationale, or title.

## 3 - ✅ A restricted push title carries no finding detail

`build_preview` (`notifications/preview.py:11`) uses `RESTRICTED_TITLE`
(`notifications/preview.py:8`) when confidentiality is restricted. The title is
`Review finding needs attention`. File, line, and finding title stay in the body,
not the title (`test_restricted_preview_title_has_no_finding_detail`).

## 4 - ✅ Inconclusive cannot auto-post

Failed or inconclusive verification queues for a person
(`notifications/gate.py:48`). Analysis-only forces human approval
(`tests/test_runner_modes.py`). Stale head does not post
(`tests/test_post_review.py`).

## 5 - ✅ Human decisions are append-only

`record_human_feedback` (`notifications/feedback.py:13`) writes actor, action,
note, and hashes. It does not update prompts. One dispute does not rewrite
policy (`tests/test_human_feedback.py`). Dashboard pending approvals and an
approval race live on the loopback API (`tests/test_dashboard_api.py`).

## Design gate - ✅

✅ A public-safe verified finding can reach approval. A high security finding
routes privately. A restricted push title has no finding detail. Inconclusive
cannot auto-post. Human decisions append.

## Test gate - ✅ reproduced

The proof gate is: a public-safe verified finding can reach approval, a high
security finding routes privately to a channel declared restricted, a restricted
push title carries no finding detail, an inconclusive finding cannot auto-post,
and every human decision is append-only.

Command, run 2026-09-01 against this checkout:

```text
$ flock -w 3600 /tmp/pr-reviewer-pytest.lock uv run pytest -q tests/test_dashboard_auth.py::test_unauthenticated_docs_and_unknown_paths_are_not_ok tests/test_notification_policy.py tests/test_notification_dispatch.py tests/test_notification_channels_hosted.py tests/test_human_feedback.py tests/test_dashboard_api.py::test_pending_approvals_list tests/test_dashboard_api.py::test_approval_race_returns_conflict tests/test_runner_modes.py::test_analysis_only_sets_retrieval_and_verification_false_and_forces_human_approval tests/test_post_review.py::test_stale_head_sha_does_not_post
...........................                                              [100%]
27 passed, 1 warning in 1.55s
```

`test_unauthenticated_docs_and_unknown_paths_are_not_ok` is the 06:11 FIX.

⚠️ Task 24 (FoodSpector shadow) and runtime Task 10 are not this gate.

## Settled - ✅

- ✅ Routing is system-owned. Confidence is not a posting decision.
- ✅ `HOSTED_EXEMPTIONS` stays empty.

## Open Decisions - ❓

- ❓ None for this HITL gate. Public deploy remains runtime Task 10.

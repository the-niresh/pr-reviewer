"""HTTP surface for one-time runner pairing (Runtime Task 2).

Only the steps that need no unverified authorization claim are exposed here: a runner creating a
pairing code, a runner exchanging one that was approved out-of-band, and a runner rotating its own
credential. Approving a code needs a real, GitHub-verified VerifiedInstallationAccess, and this
task does not build the OAuth flow that produces one safely, so there is deliberately no HTTP
route here for it yet. Adding one before Task 2A wires real OAuth would mean trusting whatever
installation_id and user_id a client cared to send, which is exactly the class of bug
docs/phases/phase-2-security-design-gate.md exists to keep out.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from pr_reviewer.contracts.runner import AssignmentRefused, PairingDenied, RunnerAuthDenied
from pr_reviewer.control_plane.pairing import create_pairing_code, exchange_pairing_code
from pr_reviewer.control_plane.runner_auth import authenticate_runner, rotate_runner_credential

router = APIRouter(prefix="/api/runner", tags=["runner-pairing"])


class CreatePairingCodeRequest(BaseModel):
    device_name: str
    challenge: str


class ExchangePairingCodeRequest(BaseModel):
    code: str
    proof: str


@router.post("/pairing-codes")
def create_pairing_code_route(body: CreatePairingCodeRequest) -> dict[str, str]:
    challenge = create_pairing_code(body.device_name, body.challenge)
    return {"code": challenge.code, "expires_at": challenge.expires_at.isoformat()}


@router.post("/pairing-codes/exchange")
def exchange_pairing_code_route(body: ExchangePairingCodeRequest) -> dict[str, str]:
    result = exchange_pairing_code(body.code, body.proof)
    if isinstance(result, PairingDenied):
        raise HTTPException(status_code=400, detail=result.reason)
    if isinstance(result, AssignmentRefused):
        raise HTTPException(
            status_code=409,
            detail=(
                f"repository already assigned to runner {result.active_runner.device_name}"
                f" ({result.active_runner.runner_id}); revoke it there first"
            ),
        )
    return {"runner_id": str(result.runner_id), "credential": result.credential}


@router.post("/credential/rotate")
def rotate_runner_credential_route(
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer credential")
    credential = authorization.removeprefix("Bearer ")

    authenticated = authenticate_runner(credential)
    if isinstance(authenticated, RunnerAuthDenied):
        raise HTTPException(status_code=401, detail=authenticated.reason)

    # The same credential the caller just authenticated with is also the "current credential"
    # rotate_runner_credential re-checks; there is no second secret to prove possession of.
    result = rotate_runner_credential(authenticated.runner_id, credential)
    if isinstance(result, RunnerAuthDenied):
        raise HTTPException(status_code=401, detail=result.reason)
    return {"runner_id": str(result.runner_id), "credential": result.credential}

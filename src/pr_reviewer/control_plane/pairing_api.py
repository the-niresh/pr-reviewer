"""HTTP surface for one-time runner pairing (Runtime Task 2 and 2B).

Runner-facing routes only: create a pairing code, poll whether it is exchangeable, exchange it,
rotate a credential. Approval is not here. It lives on the hosted dashboard under
control_plane/approval_api.py and consumes a live GitHub sign-in rather than trusting a
caller-supplied github_user_id and installation_id.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from pr_reviewer.contracts.runner import AssignmentRefused, PairingDenied, RunnerAuthDenied
from pr_reviewer.control_plane.installation_token import (
    RunnerInstallationToken,
    RunnerInstallationTokenDenied,
    issue_runner_installation_token,
)
from pr_reviewer.control_plane.pairing import (
    create_pairing_code,
    exchange_pairing_code,
    pairing_status,
)
from pr_reviewer.control_plane.runner_auth import authenticate_runner, rotate_runner_credential
from pr_reviewer.db.client import connection

router = APIRouter(prefix="/api/runner", tags=["runner-pairing"])


class CreatePairingCodeRequest(BaseModel):
    device_name: str
    challenge: str


class ExchangePairingCodeRequest(BaseModel):
    code: str
    proof: str


class RunnerInstallationRepository(BaseModel):
    github_repository_id: int
    name: str


class RunnerInstallationSnapshot(BaseModel):
    github_login: str
    github_user_id: int
    installation_id: int
    repositories: list[RunnerInstallationRepository]


@router.post("/pairing-codes")
def create_pairing_code_route(body: CreatePairingCodeRequest) -> dict[str, str]:
    challenge = create_pairing_code(body.device_name, body.challenge)
    return {"code": challenge.code, "expires_at": challenge.expires_at.isoformat()}


@router.get("/pairing-codes/status")
def pairing_status_route(code: str, challenge: str) -> dict[str, str]:
    return {"state": pairing_status(code, challenge)}


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


@router.get("/installation")
def runner_installation_route(
    authorization: str | None = Header(default=None),
) -> RunnerInstallationSnapshot:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer credential")
    authenticated = authenticate_runner(authorization.removeprefix("Bearer "))
    if isinstance(authenticated, RunnerAuthDenied):
        raise HTTPException(status_code=401, detail=authenticated.reason)

    with connection() as conn:
        rows = conn.execute(
            """
            select runners.github_user_id, runners.installation_id, installations.account_login,
                   repositories.github_repository_id, repositories.name
            from runners
            join installations on installations.id = runners.installation_id
              and installations.revoked_at is null
            left join repository_assignments on repository_assignments.runner_id = runners.id
            left join repositories on repositories.id = repository_assignments.repository_id
              and repositories.installation_id = runners.installation_id
            where runners.id = %s
            order by repositories.github_repository_id
            """,
            (str(authenticated.runner_id),),
        ).fetchall()

    if not rows or rows[0]["github_user_id"] is None:
        raise HTTPException(status_code=404, detail="runner installation is unavailable")
    first = rows[0]
    repositories = [
        RunnerInstallationRepository(
            github_repository_id=int(row["github_repository_id"]), name=str(row["name"])
        )
        for row in rows
        if row["github_repository_id"] is not None
    ]
    return RunnerInstallationSnapshot(
        github_login=str(first["account_login"]),
        github_user_id=int(first["github_user_id"]),
        installation_id=int(first["installation_id"]),
        repositories=repositories,
    )


@router.post("/installations/{installation_id}/token")
def issue_installation_token_route(
    installation_id: int,
    authorization: str | None = Header(default=None),
) -> RunnerInstallationToken:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer credential")
    credential = authorization.removeprefix("Bearer ")
    authenticated = authenticate_runner(credential)
    if isinstance(authenticated, RunnerAuthDenied):
        raise HTTPException(status_code=401, detail=authenticated.reason)
    try:
        return issue_runner_installation_token(authenticated.runner_id, installation_id)
    except RunnerInstallationTokenDenied as denied:
        raise HTTPException(status_code=403, detail=denied.reason) from denied

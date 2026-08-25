from __future__ import annotations

import hmac
import re
from hashlib import sha256

SIGNATURE_PREFIX = "sha256="
SIGNATURE_PATTERN = re.compile(r"^[a-f0-9]{64}$", re.IGNORECASE)


def verify_github_signature(body: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature.startswith(SIGNATURE_PREFIX):
        return False

    signature_hex = signature[len(SIGNATURE_PREFIX) :]
    if SIGNATURE_PATTERN.fullmatch(signature_hex) is None:
        return False

    expected = hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()
    return hmac.compare_digest(signature_hex.lower(), expected)

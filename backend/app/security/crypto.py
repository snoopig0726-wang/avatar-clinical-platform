from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken as FernetInvalidToken


class InvalidToken(ValueError):
    pass


class SensitiveTextDecryptionError(ValueError):
    pass


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_secret(secret: str, key: str, purpose: str) -> bytes:
    return hmac.new(key.encode(), f"{purpose}:{secret}".encode(), hashlib.sha256).digest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${_b64url(salt)}${_b64url(derived)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode(),
            salt=_b64url_decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return hmac.compare_digest(derived, _b64url_decode(expected))
    except (ValueError, TypeError):
        return False


def encode_staff_token(payload: dict[str, Any], secret_key: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_part = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_part = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(
        secret_key.encode(), f"{header_part}.{payload_part}".encode(), hashlib.sha256
    ).digest()
    return f"{header_part}.{payload_part}.{_b64url(signature)}"


def decode_staff_token(token: str, secret_key: str) -> dict[str, Any]:
    try:
        header_part, payload_part, signature_part = token.split(".")
        expected = hmac.new(
            secret_key.encode(), f"{header_part}.{payload_part}".encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature_part)):
            raise InvalidToken("invalid signature")
        payload = json.loads(_b64url_decode(payload_part))
        if int(payload["exp"]) <= int(datetime.now(UTC).timestamp()):
            raise InvalidToken("expired token")
        return payload
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidToken("invalid token") from exc


def derive_invite_code(invite_id: UUID, secret_key: str) -> str:
    digest = hmac.new(secret_key.encode(), f"invite:{invite_id}".encode(), hashlib.sha256).digest()
    compact = base64.b32encode(digest).decode("ascii").rstrip("=")[:12]
    return "-".join(compact[index : index + 4] for index in range(0, 12, 4))


def normalize_invite_code(code: str) -> str:
    return "".join(character for character in code.upper() if character.isalnum())


def derive_patient_token(session_id: UUID, secret_key: str) -> str:
    signature = hmac.new(
        secret_key.encode(), f"patient-session:{session_id}".encode(), hashlib.sha256
    ).digest()[:24]
    return f"pt_{_b64url(session_id.bytes + signature)}"


def _field_fernet(secret_key: str) -> Fernet:
    derived_key = hashlib.sha256(f"field-encryption:{secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived_key))


def encrypt_sensitive_text(text: str, secret_key: str) -> bytes:
    """Encrypt short-lived clinical free text before database persistence."""
    return _field_fernet(secret_key).encrypt(text.encode("utf-8"))


def decrypt_sensitive_text(ciphertext: bytes, secret_key: str) -> str:
    try:
        return _field_fernet(secret_key).decrypt(ciphertext).decode("utf-8")
    except (FernetInvalidToken, UnicodeDecodeError) as exc:
        raise SensitiveTextDecryptionError("sensitive text could not be decrypted") from exc

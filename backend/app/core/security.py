"""Cryptographic security utilities, password hashing, tokens, and role permissions."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
from enum import Enum
from typing import ClassVar


class SystemRole(str, Enum):
    """Platform-level system roles."""
    PLATFORM_ADMIN = "platform_admin"
    STANDARD_USER = "standard_user"


class SecurityRole:
    """Standardized multi-tenant RBAC role definitions."""
    TENANT_ADMIN = "tenant_admin"
    AGENT_OPERATOR = "agent_operator"
    READ_ONLY = "read_only"

    # Recognized role aliases
    ADMIN_ROLES: ClassVar[set[str]] = {"owner", "admin", "tenant_admin"}
    OPERATOR_ROLES: ClassVar[set[str]] = {"owner", "admin", "tenant_admin", "member", "agent_operator"}
    READ_ONLY_ROLES: ClassVar[set[str]] = {"viewer", "read_only"}

    @classmethod
    def is_write_permitted(cls, role: str) -> bool:
        """Verify whether a role is permitted to perform mutation operations (POST, PATCH, DELETE)."""
        normalized = role.lower().strip()
        if normalized in cls.READ_ONLY_ROLES:
            return False
        return normalized in cls.OPERATOR_ROLES

    @classmethod
    def is_admin_permitted(cls, role: str) -> bool:
        """Verify whether a role has administrative authority over tenant resources."""
        return role.lower().strip() in cls.ADMIN_ROLES


# --- Password Hashing (OWASP Salted PBKDF2-HMAC-SHA256) ---

PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 600_000
SALT_BYTES = 16


def hash_password(plain_password: str) -> str:
    """Securely hash a password using salted PBKDF2-HMAC-SHA256 with 600,000 iterations."""
    salt = secrets.token_bytes(SALT_BYTES)
    derived_key = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        plain_password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    key_b64 = base64.b64encode(derived_key).decode("ascii")
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt_b64}${key_b64}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against an encoded PBKDF2 hash using constant-time comparison."""
    try:
        parts = hashed_password.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2].encode("ascii"))
        expected_key = base64.b64decode(parts[3].encode("ascii"))

        candidate_key = hashlib.pbkdf2_hmac(
            PBKDF2_ALGORITHM,
            plain_password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(candidate_key, expected_key)
    except (ValueError, TypeError, binascii.Error, IndexError, KeyError):
        return False


# --- Session Tokens ---

def generate_session_token() -> str:
    """Generate a high-entropy URL-safe bearer session token."""
    return f"agyt_{secrets.token_urlsafe(32)}"


def hash_session_token(token: str) -> str:
    """Compute a SHA-256 digest of a session token for secure database indexing."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

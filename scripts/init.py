"""Create a local .env with generated secrets and Ed25519 JWT signing keys.

Idempotent: existing non-empty values and keys are never overwritten. Newly generated demo
passwords are printed once, here, and live only in the git-ignored .env afterwards.

Usage: python scripts/init.py [--rotate-keys]
"""

from __future__ import annotations

import argparse
import secrets
import shutil
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
KEYS_DIR = ROOT / "secrets" / "jwt"
ACTIVE_KID_FILE = "active_kid"
KEYS_TO_KEEP = 2
PASSWORD_BYTES = 18  # 24 url-safe characters, comfortably above the 12-character minimum
DB_PASSWORD_BYTES = 24

GENERATED = {
    "POSTGRES_PASSWORD": DB_PASSWORD_BYTES,
    "DEMO_ADMIN_PASSWORD": PASSWORD_BYTES,
    "DEMO_ESTIMATOR_PASSWORD": PASSWORD_BYTES,
    "DEMO_APPROVER_PASSWORD": PASSWORD_BYTES,
    "DEMO_VIEWER_PASSWORD": PASSWORD_BYTES,
}


def ensure_env() -> dict[str, str]:
    """Fill blank generated values in .env; return the newly generated ones."""
    if not ENV_FILE.exists():
        shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    created: dict[str, str] = {}
    out: list[str] = []
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and key in GENERATED and not value.strip():
            created[key] = secrets.token_urlsafe(GENERATED[key])
            out.append(f"{key}={created[key]}")
        else:
            out.append(line)
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    ENV_FILE.chmod(0o600)
    return created


def generate_key() -> str:
    """Write a new Ed25519 private key, mark it active, prune old keys. Returns its key ID."""
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    kid = secrets.token_hex(8)
    pem = Ed25519PrivateKey.generate().private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_file = KEYS_DIR / f"{kid}.pem"
    key_file.write_bytes(pem)
    # Readable by the API container's non-root user through the bind mount (local dev only;
    # deployed environments use Secret Manager / Kubernetes Secrets, see docs/RUNBOOK.md).
    key_file.chmod(0o644)
    (KEYS_DIR / ACTIVE_KID_FILE).write_text(kid + "\n", encoding="utf-8")
    keys = sorted(KEYS_DIR.glob("*.pem"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in keys[KEYS_TO_KEEP:]:
        stale.unlink()
    return kid


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rotate-keys", action="store_true", help="add a new active signing key")
    args = parser.parse_args()

    created = ensure_env()
    has_key = (KEYS_DIR / ACTIVE_KID_FILE).exists()
    if args.rotate_keys or not has_key:
        kid = generate_key()
        print(f"Signing key {kid} is now active in secrets/jwt/ (previous key kept for rollover).")
    else:
        print("Signing keys already present in secrets/jwt/.")

    if created:
        print("\nGenerated new secrets in .env (shown once; .env is git-ignored):")
        for key, value in created.items():
            if key.startswith("DEMO_"):
                print(f"  {key}={value}")
        print("  POSTGRES_PASSWORD=<hidden>" if "POSTGRES_PASSWORD" in created else "", end="")
        print()
    else:
        print(".env already complete. Demo credentials are the DEMO_* entries in .env.")


if __name__ == "__main__":
    main()

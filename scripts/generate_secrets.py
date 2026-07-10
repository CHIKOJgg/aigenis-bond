#!/usr/bin/env python3
"""Generate cryptographically secure credentials for production deployment.

Usage:
    python scripts/generate_secrets.py              # print to stdout
    python scripts/generate_secrets.py --write-env   # update .env (creates backup)
"""
from __future__ import annotations

import argparse
import secrets
import shutil
import string
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"
ENV_BACKUP = REPO_ROOT / ".env.bak"


def random_password(length: int = 24) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    return "".join(secrets.choice(chars) for _ in range(length))


def random_jwt_secret() -> str:
    return secrets.token_hex(64)


def random_db_password() -> str:
    return secrets.token_urlsafe(20)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate production secrets")
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="Write generated secrets into .env (creates backup)",
    )
    parser.add_argument(
        "--docker-secrets",
        action="store_true",
        help="Write secrets into docker/ secrets directory",
    )
    args = parser.parse_args()

    secrets_map = {
        "JWT_SECRET_KEY": random_jwt_secret(),
        "ADMIN_PASSWORD": random_password(24),
        "POSTGRES_PASSWORD": random_db_password(),
        "REDIS_PASSWORD": random_db_password(),
        "ENCRYPTION_KEY": secrets.token_hex(32),
    }

    if args.write_env:
        if not ENV_FILE.exists():
            print(f"ERROR: {ENV_FILE} not found. Create it from .env.example first.")
            sys.exit(1)

        shutil.copy2(ENV_FILE, ENV_BACKUP)
        print(f"Backup created: {ENV_BACKUP}")

        content = ENV_FILE.read_text(encoding="utf-8")

        # Write each new secret
        for key, value in secrets_map.items():
            # Try to find and replace existing value
            import re

            pattern = re.compile(rf"^{key}=.*", re.MULTILINE)
            if pattern.search(content):
                content = pattern.sub(f"{key}={value}", content)
            else:
                content += f"\n{key}={value}\n"

        # Also update DB passwords in DATABASE_URL
        db_password = secrets_map["POSTGRES_PASSWORD"]
        content = re.sub(
            r"(postgresql\+asyncpg://aigenis:)[^@]+(@)",
            rf"\g<1>{db_password}\g<2>",
            content,
        )
        content = re.sub(
            r"(postgresql://aigenis:)[^@]+(@)",
            rf"\g<1>{db_password}\g<2>",
            content,
        )

        # Redis password
        redis_password = secrets_map["REDIS_PASSWORD"]
        content = re.sub(
            r"(redis://)([^:]+)(:[^@]*@)",
            rf"\g<1>\g<2>:{redis_password}@",
            content,
        )

        ENV_FILE.write_text(content, encoding="utf-8")
        print(f"Secrets written to {ENV_FILE}")

    if args.docker_secrets:
        secrets_dir = REPO_ROOT / "docker" / "secrets"
        secrets_dir.mkdir(parents=True, exist_ok=True)

        for key, value in secrets_map.items():
            secret_file = secrets_dir / key.lower()
            secret_file.write_text(value, encoding="utf-8")
            print(f"Docker secret written: {secret_file}")

        # Also create .gitkeep for empty dirs
        (secrets_dir / ".gitkeep").write_text("")

    if not args.write_env and not args.docker_secrets:
        print("=" * 60)
        print("Generated Production Secrets")
        print("=" * 60)
        for key, value in secrets_map.items():
            print(f"\n{key}={value}")

        print("\n\nInstructions:")
        print("  python scripts/generate_secrets.py --write-env")
        print("  python scripts/generate_secrets.py --docker-secrets")


if __name__ == "__main__":
    main()

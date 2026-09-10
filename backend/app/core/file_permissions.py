"""Best-effort private permissions for local sensitive application data."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from app.core.subprocess_env import safe_subprocess_env

logger = logging.getLogger(__name__)


def _windows_principal(executable: str) -> str:
    process = subprocess.run(
        [executable],
        env=safe_subprocess_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    principal = (process.stdout or "").strip()
    if process.returncode != 0 or "\\" not in principal:
        raise RuntimeError("could not resolve the current Windows security principal")
    return principal


def harden_private_path(path: str | Path, *, recursive: bool = False) -> bool:
    target = Path(path).resolve()
    if not target.exists():
        return True
    if os.name != "nt":
        try:
            target.chmod(0o700 if target.is_dir() else 0o600)
            if recursive and target.is_dir():
                for child in target.rglob("*"):
                    child.chmod(0o700 if child.is_dir() else 0o600)
            return True
        except OSError:
            logger.warning("Could not restrict permissions for %s", target, exc_info=True)
            return False

    icacls = shutil.which("icacls.exe") or shutil.which("icacls")
    if not icacls:
        logger.warning("icacls not found; permissions were not restricted for %s", target)
        return False
    whoami = shutil.which("whoami.exe") or shutil.which("whoami")
    if not whoami:
        logger.warning("whoami not found; permissions were not restricted for %s", target)
        return False
    try:
        principal = _windows_principal(whoami)
    except RuntimeError:
        logger.warning("Current Windows principal could not be resolved", exc_info=True)
        return False
    interactive_user = "\\".join(
        part for part in (os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", "")) if part
    )
    principals = [principal]
    if interactive_user and interactive_user.lower() != principal.lower():
        principals.append(interactive_user)
    suffix = "(OI)(CI)F" if target.is_dir() else "F"
    command = [
        icacls,
        str(target),
        "/inheritance:r",
    ]
    for identity in principals:
        command.extend(["/grant:r", f"{identity}:{suffix}"])
    command.extend(
        [
            "/grant:r",
            f"*S-1-5-18:{suffix}",
            "/grant:r",
            f"*S-1-5-32-544:{suffix}",
        ]
    )
    process = subprocess.run(
        command,
        env=safe_subprocess_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if process.returncode != 0:
        logger.warning("icacls failed for %s: %s", target, (process.stderr or "").strip())
        return False

    if recursive and target.is_dir() and any(target.iterdir()):
        # Apply inheritable ACEs only to the directory root. Passing the same
        # ``(OI)(CI)`` grant recursively makes icacls apply directory
        # inheritance flags directly to files and can leave those files with
        # unusable ACLs. Reset descendants instead so they inherit the private
        # root ACL with the correct file/directory form.
        reset_process = subprocess.run(
            [icacls, str(target / "*"), "/reset", "/T", "/C", "/Q"],
            env=safe_subprocess_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if reset_process.returncode != 0:
            logger.warning(
                "icacls descendant reset failed for %s: %s",
                target,
                (reset_process.stderr or "").strip(),
            )
            return False
    return True

"""Minimal environment construction for local child processes."""

from __future__ import annotations

import os
from collections.abc import Mapping


_ALLOWED_NAMES = {
    "ALLUSERSPROFILE",
    "APPDATA",
    "COMSPEC",
    "CONDA_DEFAULT_ENV",
    "CONDA_PREFIX",
    "CONDA_SHLVL",
    "HOMEDRIVE",
    "HOMEPATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LOCALAPPDATA",
    "NUMBER_OF_PROCESSORS",
    "PATH",
    "PATHEXT",
    "PROCESSOR_ARCHITECTURE",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "PYTHONHOME",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USERDOMAIN",
    "USERNAME",
    "USERPROFILE",
    "WINDIR",
}


def safe_subprocess_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return an allowlisted environment with no inherited API secrets."""
    environment = {
        name: value
        for name, value in os.environ.items()
        if name.upper() in _ALLOWED_NAMES
    }
    if extra:
        environment.update({name: str(value) for name, value in extra.items()})
    return environment

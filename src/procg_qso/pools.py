"""Load persona/QSO value pools from editable text files.

Each pool is one file under ``procg_qso/data/pools`` (e.g. ``rigs.txt``), one
entry per line. Blank lines and lines starting with ``#`` are ignored, so files
can carry a header or commented-out entries. Add or remove variety by editing
the files and re-running (restart the kernel in a notebook). No code changes.
"""
from __future__ import annotations
from functools import lru_cache
from importlib.resources import files

_ANCHOR = "procg_qso.data.pools"


@lru_cache(maxsize=None)
def load(name: str) -> tuple[str, ...]:
    """Entries of one pool as a tuple (cached)."""
    try:
        text = files(_ANCHOR).joinpath(f"{name}.txt").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as e:
        raise FileNotFoundError(
            f"value pool {name!r} not found at procg_qso/data/pools/{name}.txt"
        ) from e
    entries = [ln.strip() for ln in text.splitlines()
               if ln.strip() and not ln.strip().startswith("#")]
    if not entries:
        raise ValueError(f"value pool {name!r} is empty")
    return tuple(entries)


def available() -> list[str]:
    """Names of all pools present (filename without .txt)."""
    try:
        return sorted(p.name[:-4] for p in files(_ANCHOR).iterdir()
                      if p.name.endswith(".txt") and not p.name.startswith("__"))
    except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError):
        return []

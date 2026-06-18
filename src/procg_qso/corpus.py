"""Load bundled CW-practice corpora.

Corpora ship inside the package under ``procg_qso/data/corpora`` as plain text,
one sentence per line, restricted to CW-sendable punctuation (. , ? /). Access
them through ``importlib.resources`` so they resolve from source or wheel alike.
All lookups degrade to empty rather than raising, so text generation still works
if no corpus is installed.
"""
from __future__ import annotations
from functools import lru_cache
from importlib.resources import files

_ANCHOR = "procg_qso.data.corpora"


def available() -> list[str]:
    """Names of bundled corpora (filename without .txt). Empty if none."""
    try:
        return sorted(p.name[:-4] for p in files(_ANCHOR).iterdir()
                      if p.name.endswith(".txt"))
    except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError):
        return []


@lru_cache(maxsize=None)
def load(name: str = "collins_1922") -> tuple[str, ...]:
    """One corpus as a tuple of sentences (cached)."""
    text = files(_ANCHOR).joinpath(f"{name}.txt").read_text(encoding="utf-8")
    return tuple(line for line in text.splitlines() if line.strip())


@lru_cache(maxsize=1)
def default_corpus() -> tuple[str, ...]:
    """Every bundled corpus concatenated. Empty tuple if none present."""
    out: list[str] = []
    for name in available():
        out.extend(load(name))
    return tuple(out)

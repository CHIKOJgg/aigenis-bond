"""ML model registry: artifact persistence, caching, champion promotion,
pruning and lightweight drift metrics.

Historically ``ml/engine.py`` dumped every trained model with ``pickle`` into a
flat directory and ``latest_artifact`` simply returned the newest file. That
meant:
* no stable "champion" — a half-trained or regressed model could become live
  just by being the most recent file;
* no upper bound on artifact growth (the directory accumulated 150+ pickles);
* every prediction re-loaded the artifact from disk.

This module centralises artifact handling. Existing ``.pkl`` files remain
readable (the loader falls back to ``pickle``), but new artifacts are written
with ``joblib`` and served through an in-memory LRU cache.
"""

from __future__ import annotations

import functools
import math
import pickle
from itertools import chain
from pathlib import Path

import joblib

from ml.models import ModelKind

ARTIFACTS_DIR = Path("ml/artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

_KIND_PREFIX: dict[ModelKind, str] = {
    "ytm_regression": "ytm_regressor_",
    "buy_classifier": "buy_classifier_",
    "volatility": "volatility_",
}

_SUFFIX_JOBLIB = ".joblib"
_SUFFIX_PICKLE = ".pkl"


def artifact_path(kind: ModelKind, version: str, *, joblib_format: bool = True) -> Path:
    suffix = _SUFFIX_JOBLIB if joblib_format else _SUFFIX_PICKLE
    return ARTIFACTS_DIR / f"{_KIND_PREFIX[kind]}{version}{suffix}"


def save_artifact(path: str | Path, bundle: dict) -> None:
    """Persist a model bundle with joblib (sklearn-safe, faster than pickle).

    ``compress=0`` keeps the dependency footprint minimal (no ``lz4`` needed).
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, str(p), compress=0)


@functools.lru_cache(maxsize=8)
def load_artifact_cached(path: str) -> dict:
    """Load a model bundle, caching by path.

    joblib first (new artifacts), pickle fallback (legacy ``.pkl``).
    """
    p = Path(path)
    if p.suffix == _SUFFIX_PICKLE:
        with open(p, "rb") as fh:
            return pickle.load(fh)
    try:
        return joblib.load(str(p))
    except Exception:
        if p.exists():
            with open(p, "rb") as fh:
                return pickle.load(fh)
        raise


def champion_pointer_path(kind: ModelKind) -> Path:
    return ARTIFACTS_DIR / f"champion_{_KIND_PREFIX[kind].rstrip('_')}.txt"


def promote_champion(kind: ModelKind, version: str) -> None:
    """Mark ``version`` as the champion for ``kind`` via a pointer file."""
    champion_pointer_path(kind).write_text(version, encoding="utf-8")


def get_champion(kind: ModelKind) -> str | None:
    ptr = champion_pointer_path(kind)
    if not ptr.exists():
        return None
    value = ptr.read_text(encoding="utf-8").strip()
    return value or None


def latest_artifact(kind: ModelKind) -> str | None:
    """Return the artifact path to serve.

    Prefers the explicit champion (if its file still exists), otherwise the
    most recently written artifact of that kind.
    """
    champion = get_champion(kind)
    if champion:
        for suffix in (_SUFFIX_JOBLIB, _SUFFIX_PICKLE):
            cand = ARTIFACTS_DIR / f"{_KIND_PREFIX[kind]}{champion}{suffix}"
            if cand.exists():
                return str(cand)

    files = sorted(
        chain(
            ARTIFACTS_DIR.glob(f"{_KIND_PREFIX[kind]}*{_SUFFIX_JOBLIB}"),
            ARTIFACTS_DIR.glob(f"{_KIND_PREFIX[kind]}*{_SUFFIX_PICKLE}"),
        ),
        key=lambda p: p.stat().st_mtime,
    )
    if not files:
        return None
    return str(files[-1])


def prune_artifacts(keep: int = 5) -> list[str]:
    """Delete all but the ``keep`` newest artifacts per kind.

    The champion artifact (if any) is always preserved even if it is older
    than the ``keep`` newest. Returns the list of removed paths.
    """
    removed: list[str] = []
    champions = {k: get_champion(k) for k in _KIND_PREFIX}
    for kind in _KIND_PREFIX:
        files = sorted(
            chain(
                ARTIFACTS_DIR.glob(f"{_KIND_PREFIX[kind]}*{_SUFFIX_JOBLIB}"),
                ARTIFACTS_DIR.glob(f"{_KIND_PREFIX[kind]}*{_SUFFIX_PICKLE}"),
            ),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        champ = champions[kind]
        champ_name = f"{_KIND_PREFIX[kind]}{champ}" if champ else None
        for f in files[keep:]:
            if champ_name and f.stem == champ_name:
                continue
            f.unlink()
            removed.append(str(f))
    return removed


def population_stability_index(expected: list[float], actual: list[float], bins: int = 10) -> float:
    """Compute the Population Stability Index between two feature distributions.

    PSI > 0.25 signals meaningful drift that should trigger model review.
    Empty inputs return 0.0 (no signal), not an error.
    """
    if not expected or not actual:
        return 0.0

    lo = min(expected + actual)
    hi = max(expected + actual)
    if hi == lo:
        return 0.0
    width = (hi - lo) / bins

    def _dist(values: list[float]) -> list[float]:
        counts = [0] * bins
        for v in values:
            idx = min(bins - 1, int((v - lo) / width))
            counts[idx] += 1
        return [c / len(values) for c in counts]

    exp = _dist(expected)
    act = _dist(actual)
    psi = 0.0
    for e, a in zip(exp, act, strict=True):
        if e <= 0:
            e = 1e-6
        if a <= 0:
            a = 1e-6
        # True Population Stability Index: sum of (actual - expected) * ln(actual/expected).
        psi += (a - e) * math.log(a / e)
    return psi

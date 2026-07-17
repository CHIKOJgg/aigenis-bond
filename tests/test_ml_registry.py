from __future__ import annotations

import pickle

import ml.registry as registry
from ml.models import ModelKind
from ml.registry import (
    get_champion,
    latest_artifact,
    load_artifact_cached,
    population_stability_index,
    promote_champion,
    prune_artifacts,
    save_artifact,
)


def _touch(kind: ModelKind, version: str, *, legacy: bool = False) -> str:
    suffix = ".pkl" if legacy else ".joblib"
    prefix = "ytm_regressor_" if kind == "ytm_regression" else "buy_classifier_"
    path = registry.ARTIFACTS_DIR / f"{prefix}{version}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {"model": "m", "scaler": "s", "features": ["a"]}
    if legacy:
        with open(path, "wb") as fh:
            pickle.dump(bundle, fh)
    else:
        save_artifact(path, bundle)
    return str(path)


def test_save_and_cached_load_joblib(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ARTIFACTS_DIR", tmp_path / "artifacts")
    path = tmp_path / "artifacts" / "ytm_regressor_x.joblib"
    bundle = {"model": "m", "scaler": "s", "features": ["a"]}
    save_artifact(path, bundle)
    assert load_artifact_cached(str(path)) == bundle
    # second call hits the cache (no file change)
    assert load_artifact_cached(str(path)) == bundle


def test_load_legacy_pickle_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ARTIFACTS_DIR", tmp_path / "artifacts")
    p = tmp_path / "artifacts" / "ytm_regressor_old.pkl"
    p.parent.mkdir(parents=True, exist_ok=True)
    bundle = {"model": 1, "scaler": 2, "features": ["x"]}
    with open(p, "wb") as fh:
        pickle.dump(bundle, fh)
    assert load_artifact_cached(str(p)) == bundle


def test_champion_promotion_and_latest_prefers_champion(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ARTIFACTS_DIR", tmp_path / "artifacts")
    old = _touch("ytm_regression", "20200101000000")
    new = _touch("ytm_regression", "20210101000000")
    # without champion, latest is the newest file (new)
    assert latest_artifact("ytm_regression") == new
    # promote the older one -> champion wins
    promote_champion("ytm_regression", "20200101000000")
    assert get_champion("ytm_regression") == "20200101000000"
    assert latest_artifact("ytm_regression") == old


def test_prune_artifacts_keeps_champion(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ARTIFACTS_DIR", tmp_path / "artifacts")
    versions = [f"2020010{i}000000" for i in range(7)]
    for v in versions:
        _touch("ytm_regression", v)
    # champion the oldest (would otherwise be pruned)
    promote_champion("ytm_regression", versions[0])
    prune_artifacts(keep=3)
    # 7 total, keep 3 -> 4 removed, but champion preserved
    remaining = list((tmp_path / "artifacts").glob("ytm_regressor_*.joblib"))
    assert len(remaining) == 4  # 3 newest + champion
    assert any(p.name.endswith(f"{versions[0]}.joblib") for p in remaining)


def test_population_stability_index_no_signal_for_empty():
    assert population_stability_index([], []) == 0.0


def test_population_stability_index_low_for_similar():
    a = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    b = [1.1, 2.1, 2.9, 4.1, 5.0, 6.2, 6.9, 8.1, 9.0, 9.9]
    assert population_stability_index(a, b) < 0.25  # similar distributions


def test_population_stability_index_high_for_drift():
    a = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    b = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0]
    assert population_stability_index(a, b) > 0.25

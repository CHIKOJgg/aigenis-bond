"""Tests for the ML model registry: artifact persistence, champion promotion,
pruning and population-stability drift metric."""

from __future__ import annotations

import os
import time

import numpy as np
import pytest
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler

import ml.registry as registry


def _bundle(tmp_path):
    """Train a tiny model and persist it as a registry artifact bundle."""
    x_train = np.array([[0.0, 1.0], [1.0, 0.0], [0.5, 0.5]], dtype=float)
    y = np.array([1.0, 2.0, 1.5], dtype=float)
    scaler = StandardScaler().fit(x_train)
    model = GradientBoostingRegressor(n_estimators=10, random_state=0).fit(scaler.transform(x_train), y)
    path = tmp_path / "ytm_regressor_test.joblib"
    registry.save_artifact(path, {"model": model, "scaler": scaler, "features": ["a", "b"]})
    return path


def test_save_and_load_artifact_roundtrip(tmp_path):
    path = _bundle(tmp_path)
    loaded1 = registry.load_artifact_cached(str(path))
    loaded2 = registry.load_artifact_cached(str(path))
    assert loaded1["features"] == ["a", "b"]
    assert isinstance(loaded1["model"], GradientBoostingRegressor)
    assert isinstance(loaded1["scaler"], StandardScaler)
    # Two loads of the same artifact yield identical predictions (round-trip
    # determinism through joblib persistence).
    xt = scaler_transform(loaded1["scaler"], [[0.0, 1.0], [1.0, 0.0]])
    pred1 = list(loaded1["model"].predict(xt))
    pred2 = list(loaded2["model"].predict(xt))
    assert pred1 == pred2
    # The persisted bundle reproduces its training labels on the training points.
    assert pred1[0] == pytest.approx(1.0, abs=0.2)
    assert pred1[1] == pytest.approx(2.0, abs=0.2)


def scaler_transform(scaler, rows):
    return scaler.transform(np.array(rows, dtype=float))


def test_artifact_path_uses_kind_prefix_and_format(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ARTIFACTS_DIR", tmp_path)
    p = registry.artifact_path("ytm_regression", "20240101")
    assert p.name == "ytm_regressor_20240101.joblib"
    pkl = registry.artifact_path("buy_classifier", "20240101", joblib_format=False)
    assert pkl.name == "buy_classifier_20240101.pkl"


def test_promote_and_get_champion(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ARTIFACTS_DIR", tmp_path)
    assert registry.get_champion("ytm_regression") is None
    registry.promote_champion("ytm_regression", "v2")
    assert registry.get_champion("ytm_regression") == "v2"
    # pointer file is readable
    assert registry.champion_pointer_path("ytm_regression").read_text(encoding="utf-8") == "v2"


def test_latest_artifact_prefers_champion_then_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ARTIFACTS_DIR", tmp_path)
    # write two artifacts of the same kind with explicit, distinct mtimes
    old = tmp_path / "ytm_regressor_old.joblib"
    new = tmp_path / "ytm_regressor_new.joblib"
    old.write_bytes(b"x")
    new.write_bytes(b"y")
    now = time.time()
    os.utime(old, (now - 10, now - 10))
    os.utime(new, (now, now))
    # no champion yet -> newest by mtime
    assert registry.latest_artifact("ytm_regression").endswith("ytm_regressor_new.joblib")
    # promote an older one -> champion wins even if not newest
    registry.promote_champion("ytm_regression", "old")
    assert registry.latest_artifact("ytm_regression").endswith("ytm_regressor_old.joblib")


def test_prune_artifacts_keeps_newest_and_champion(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ARTIFACTS_DIR", tmp_path)
    for i in range(5):
        (tmp_path / f"ytm_regressor_{i}.joblib").write_bytes(b"x")
    # champion (oldest) must survive pruning
    registry.promote_champion("ytm_regression", "0")
    removed = registry.prune_artifacts(keep=2)
    # 5 total, keep 2 newest + champion => remove 2
    assert len(removed) == 2
    remaining = list(tmp_path.glob("ytm_regressor_*.joblib"))
    names = {p.name for p in remaining}
    assert "ytm_regressor_0.joblib" in names  # champion preserved
    assert "ytm_regressor_4.joblib" in names  # newest kept


def test_population_stability_index_empty_returns_zero():
    assert registry.population_stability_index([], []) == 0.0
    assert registry.population_stability_index([1.0], []) == 0.0


def test_population_stability_index_identical_is_zero():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert registry.population_stability_index(vals, vals) == 0.0


def test_population_stability_index_detects_drift():
    expected = [1.0, 2.0, 3.0, 4.0, 5.0]
    actual = [10.0, 11.0, 12.0, 13.0, 14.0]
    psi = registry.population_stability_index(expected, actual)
    assert psi > 0.25  # meaningful drift

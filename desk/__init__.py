"""Mini Fixed Income Desk: duration, yield curve, RV, carry, repo, stress."""

from __future__ import annotations

from desk import carry, duration, relative_value, repo, stress, yield_curve
from desk.models import (
    CarryTrade,
    CurvePoint,
    DurationReport,
    NelsonSiegelParams,
    RepoDeal,
    RVSignal,
    StressResult,
    StressScenario,
    YieldCurve,
)
from desk.stress import PRESET_SCENARIOS
from desk.yield_curve import fit_nelson_siegel, interpolate

__all__ = [
    "PRESET_SCENARIOS",
    "CarryTrade",
    "CurvePoint",
    "DurationReport",
    "NelsonSiegelParams",
    "RVSignal",
    "RepoDeal",
    "StressResult",
    "StressScenario",
    "YieldCurve",
    "carry",
    "duration",
    "fit_nelson_siegel",
    "interpolate",
    "relative_value",
    "repo",
    "stress",
    "yield_curve",
]

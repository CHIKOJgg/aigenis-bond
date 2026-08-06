"""SQLAlchemy ORM models (split from the former scraper/orm.py module).

All model classes are re-exported here so that ``from scraper.orm import X``
keeps working at every import site, and ``Base.metadata`` (used by alembic and
the tests) always sees the full schema.
"""

from __future__ import annotations

from scraper.orm._base import Base
from scraper.orm.bonds import (
    BondDailyAccrualORM,
    BondHistoryORM,
    BondORM,
    BondScoreORM,
    CompanyORM,
    ParseErrorORM,
)
from scraper.orm.desk import (
    CarryTradeORM,
    CurvePointORM,
    RepoDealORM,
    RVSignalORM,
    SpreadReportORM,
    StressRunORM,
)
from scraper.orm.documents import DocumentAnalysisORM
from scraper.orm.markets import FxRateORM, MetalPriceORM
from scraper.orm.ml import ModelVersionORM, PredictionORM, TrainingRunORM
from scraper.orm.partner import (
    PartnerKeyORM,
    PartnerLeadORM,
    PartnerReferralORM,
    WebhookORM,
)
from scraper.orm.portfolio import (
    BacktestORM,
    PnLSnapshotORM,
    PortfolioPositionORM,
    RebalanceHistoryORM,
    TransactionORM,
)
from scraper.orm.stocks import StockHistoryORM, StockORM
from scraper.orm.users import (
    AlertEventORM,
    AlertORM,
    AlertRuleORM,
    BillingPaymentEventORM,
    SubscriptionORM,
    UserORM,
    UserPreferencesORM,
)

__all__ = [
    "AlertEventORM",
    "AlertORM",
    "AlertRuleORM",
    "BacktestORM",
    "Base",
    "BillingPaymentEventORM",
    "BondDailyAccrualORM",
    "BondHistoryORM",
    "BondORM",
    "BondScoreORM",
    "CarryTradeORM",
    "CompanyORM",
    "CurvePointORM",
    "DocumentAnalysisORM",
    "FxRateORM",
    "MetalPriceORM",
    "ModelVersionORM",
    "ParseErrorORM",
    "PartnerKeyORM",
    "PartnerLeadORM",
    "PartnerReferralORM",
    "PnLSnapshotORM",
    "PortfolioPositionORM",
    "PredictionORM",
    "RVSignalORM",
    "RebalanceHistoryORM",
    "RepoDealORM",
    "SpreadReportORM",
    "StockHistoryORM",
    "StockORM",
    "StressRunORM",
    "SubscriptionORM",
    "TrainingRunORM",
    "TransactionORM",
    "UserORM",
    "UserPreferencesORM",
    "WebhookORM",
]

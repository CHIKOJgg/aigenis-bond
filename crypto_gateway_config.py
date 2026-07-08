# =============================================================================
# Aigenis Parser — Crypto + Stars Gateway Implementation
# =============================================================================
# 
# This file provides the configuration and setup for crypto + Stars payments.
# It replaces the Stripe dependency with crypto and Telegram Stars payment systems.
#

import os
import structlog
from typing import Dict, Any, List

# Initialize structured logging
structlog.configure(
    processors=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.Callsite PrintexceptedExceptionRenderer(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("crypto-gateway")

# Crypto Gateway Configuration
class CryptoGatewayConfig:
    """Configuration for crypto + Stars payments gateway."""

    def __init__(self):
        self.lightning_config = self._load_lightning_config()
        self.solana_config = self._load_solana_config()
        self.telegram_config = self._load_telegram_config()
        self.database_config = self._load_database_config()
        self.monitoring_config = self._load_monitoring_config()

    def _load_lightning_config(self) -> Dict[str, Any]:
        """Load Lightning Network configuration."""
        return {
            "api_url": os.getenv("LIGHTNING_API_URL", "https://api.lightningnetwork.southamerica-northeast-1.cloudobjectstorage.domain/amplify"),
            "api_key": os.getenv("LIGHTNING_API_KEY", ""),
            "node_url": os.getenv("LIGHTNING_NODE_URL", ""),
            "network": os.getenv("LIGHTNING_NETWORK", "mainnet"),
            "fee_rate": float(os.getenv("LIGHTNING_FEE_RATE", "0.0002")),
            "min_channel_capacity": int(os.getenv("LIGHTNING_MIN_CHANNEL_CAPACITY", "1000000")),
        }

    def _load_solana_config(self) -> Dict[str, Any]:
        """Load Solana blockchain configuration."""
        return {
            "rpc_url": os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"),
            "program_id": os.getenv("SOLANA_PROGRAM_ID", "TokenkMvTr111tMZ8Xmh1RfAwQNsXvEqHwJ"),
            "network": os.getenv("SOLANA_NETWORK", "mainnet"),
            "commitment": os.getenv("SOLANA_COMMITMENT", "finalized"),
            "max_retries": int(os.getenv("SOLANA_MAX_RETRIES", "5")),
            "retry_delay": float(os.getenv("SOLANA_RETRY_DELAY", "0.5")),
        }

    def _load_telegram_config(self) -> Dict[str, Any]:
        """Load Telegram Stars API configuration."""
        return {
            "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
            "api_url": os.getenv("TELEGRAM_API_URL", "https://api.telegram.org"),
            "stars_webhook_secret": os.getenv("TELEGRAM_STARS_WEBHOOK_SECRET", ""),
            "webhooks_configuration_url": os.getenv("TELEGRAM_WEBHOOKS_CONFIG_URL", ""),
        }

    def _load_database_config(self) -> Dict[str, Any]:
        """Load database configuration."""
        return {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "5432")),
            "name": os.getenv("DB_NAME", "aigenis"),
            "user": os.getenv("DB_USER", "aigenis"),
            "password": os.getenv("DB_PASSWORD", "aigenis"),
            "ssl_mode": os.getenv("DB_SSL_MODE", "require"),
            "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
            "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        }

    def _load_monitoring_config(self) -> Dict[str, Any]:
        """Load monitoring configuration."""
        return {
            "prometheus_enabled": os.getenv("PROMETHEUS_ENABLED", "true").lower() == "true",
            "prometheus_port": int(os.getenv("PROMETHEUS_PORT", "9090")),
            "metrics_port": int(os.getenv("METRICS_PORT", "8000")),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
            "log_format": os.getenv("LOG_FORMAT", "json"),
            "otel_exporter_url": os.getenv("OTEL_EXPORTER_URL", ""),
        }

    def get_payment_methods(self) -> List[str]:
        """Get supported payment methods."""
        return ["lightning", "solana", "telegram_stars"]

    def get_tier_prices(self) -> Dict[str, float]:
        """Get prices for subscription tiers."""
        return {
            "free": 0.0,
            "pro": 29.0,
            "enterprise": 99.0,
        }

    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "server": {
                "host": os.getenv("SERVER_HOST", "0.0.0.0"),
                "port": int(os.getenv("SERVER_PORT", "8000")),
                "workers": int(os.getenv("SERVER_WORKERS", "2")),
                "timeout": int(os.getenv("SERVER_TIMEOUT", "120")),
            },
            "crypto": {
                "minimum_amount": float(os.getenv("CRYPTO_MINIMUM_AMOUNT", "0.1")),
                "maximum_amount": float(os.getenv("CRYPTO_MAXIMUM_AMOUNT", "100000.0")),
                "supported_tokens": os.getenv("CRYPTO_SUPPORTED_TOKENS", "SOL,BTC,USDC,EUR").split(","),
            },
            "telegram": {
                "stars_per_usd": float(os.getenv("TELEGRAM_STARS_PER_USD", "85")),
                "webhook_secret": os.getenv("TELEGRAM_WEBHOOK_SECRET", ""),
            },
            "security": {
                "jwt_secret_key": os.getenv("JWT_SECRET_KEY", os.urandom(32).hex()),
                "jwt_algorithm": os.getenv("JWT_ALGORITHM", "HS256"),
                "jwt_expiry_minutes": int(os.getenv("JWT_EXPIRY_MINUTES", "30")),
            },
            "monitoring": {
                "enable_prometheus": os.getenv("ENABLE_PROMETHEUS", "true").lower() == "true",
                "prometheus_port": int(os.getenv("PROMETHEUS_PORT", "9090")),
                "log_level": os.getenv("LOG_LEVEL", "INFO"),
            },
        }

# Default configuration instance
_config: Optional[CryptoGatewayConfig] = None


def get_config() -> CryptoGatewayConfig:
    """Get the global crypto gateway configuration instance."""
    global _config
    if _config is None:
        _config = CryptoGatewayConfig()
    return _config


def init_crypto_gateway():
    """
    Initialize the crypto gateway.

    This function sets up the configuration, logging,
    and background services for the crypto payment system.
    """
    config = get_config()

    logger.info("Initializing crypto gateway configuration")

    # Log configuration details (without sensitive data)
    logger.info(
        "Crypto gateway configuration loaded",
        lightning_network=config.lightning_config["network"],
        solana_network=config.solana_config["network"],
        telegram_enabled=bool(config.telegram_config["bot_token"]),
        prometheus_enabled=config.monitoring_config["prometheus_enabled"],
        supported_payment_methods=config.get_payment_methods(),
    )

    # Log tier prices
    tier_prices = config.get_tier_prices()
    for tier, price in tier_prices.items():
        logger.info(
            "Subscription tier price",
            tier=tier,
            price=f"${price:.2f}",
        )

    logger.info("Crypto gateway initialization completed")

    return config


if __name__ == "__main__":
    """Example usage of crypto gateway configuration."""
    config = get_config()

    # Get supported payment methods
    payment_methods = config.get_payment_methods()
    print(f"Supported payment methods: {payment_methods}")

    # Get tier prices
    tier_prices = config.get_tier_prices()
    print(f"Tier prices: {tier_prices}")

    # Get default configuration
    default_config = config.get_default_config()
    print(f"Default server port: {default_config['server']['port']}")

    # Initialize the gateway
    init_crypto_gateway()
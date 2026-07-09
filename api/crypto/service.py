# Crypto Authentication Service
#
# Handles crypto wallet-based authentication and payment verification
#

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.logging import get_logger

logger = get_logger("api.auth.crypto")


class CryptoWalletAuthService:
    """
    Service for authenticating users via crypto wallets.

    This service handles:
    - Solana wallet authentication
    - Lightning Network payment authentication
    - Multi-sig wallet verification
    - Wallet-based identity verification
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config

    async def authenticate_wallet_payment(
        self,
        wallet_address: str,
        amount: float,
        expected_tier: str,
        signature: str,
        nonce: str,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """
        Authenticate a crypto wallet payment.

        Args:
            wallet_address: Wallet address making the payment
            amount: Payment amount in USD
            expected_tier: Expected subscription tier
            signature: Payment signature
            nonce: Payment nonce (for replay protection)
            session: Database session

        Returns:
            Dict with authentication result

        Raises:
            CryptoAuthError: If authentication fails
        """
        try:
            # Verify wallet signature
            if not await self._verify_wallet_signature(wallet_address, amount, expected_tier, signature, nonce):
                raise CryptoAuthError("Invalid wallet signature")

            # Get wallet balance
            wallet_balance = await self.get_wallet_balance(wallet_address)
            required_amount = self._get_tier_price(expected_tier)

            if wallet_balance < required_amount:
                raise InsufficientBalanceError(
                    f"Insufficient balance: {wallet_balance}. Required: {required_amount}"
                )

            # Update user subscription
            await self._update_user_subscription(wallet_address, expected_tier, session)

            logger.info(
                "Wallet payment authenticated",
                wallet_address=wallet_address,
                amount=amount,
                tier=expected_tier,
            )

            return {
                "authenticated": True,
                "wallet_address": wallet_address,
                "amount": amount,
                "tier": expected_tier,
                "payment_method": "crypto_wallet",
            }

        except Exception as e:
            logger.error(
                "Failed to authenticate wallet payment",
                wallet_address=wallet_address,
                amount=amount,
                error=str(e),
            )
            raise

    async def _verify_wallet_signature(
        self,
        wallet_address: str,
        amount: float,
        tier: str,
        signature: str,
        nonce: str,
    ) -> bool:
        """
        Verify a wallet signature for payment authentication.

        Args:
            wallet_address: Wallet address
            amount: Payment amount
            tier: Target tier
            signature: Signature to verify
            nonce: Nonce for replay protection

        Returns:
            True if signature is valid, False otherwise
        """
        # In production, this would verify the signature using
        # the appropriate wallet-specific cryptographic verification

        # For this example, we'll use a simple hash-based verification
        message = f"{wallet_address}:{amount}:{tier}:{nonce}"
        expected_signature = hashlib.sha256(message.encode()).hexdigest()

        return signature == expected_signature

    async def get_wallet_balance(self, wallet_address: str) -> float:
        """
        Get the balance of a crypto wallet.

        Args:
            wallet_address: Wallet address

        Returns:
            Wallet balance in USD equivalent
        """
        # In production, this would query a blockchain API
        # For this example, we'll return a dummy value
        return 100.0

    def _get_tier_price(self, tier: str) -> float:
        """
        Get the price for a subscription tier.

        Args:
            tier: Subscription tier

        Returns:
            Price in USD
        """
        prices = {
            "free": 0.0,
            "pro": 29.0,
            "enterprise": 99.0,
        }
        return prices.get(tier, 0.0)

    async def _update_user_subscription(
        self,
        wallet_address: str,
        target_tier: str,
        session: AsyncSession,
    ):
        """
        Update user's subscription based on crypto payment.

        Args:
            wallet_address: Wallet address
            target_tier: Target subscription tier
            session: Database session
        """
        from sqlalchemy import update

        from scraper.orm import UserORM

        await session.execute(
            update(UserORM)
            .where(UserORM.wallet_address == wallet_address)
            .values(subscription_tier=target_tier, updated_at=datetime.now(timezone.utc))
        )
        await session.commit()


class CryptoPaymentServiceError(Exception):
    """Base exception for crypto payment errors"""
    pass


class CryptoAuthError(CryptoPaymentServiceError):
    """Raised when crypto authentication fails"""
    pass


class WalletNotFoundError(CryptoPaymentServiceError):
    """Raised when a wallet is not found"""
    pass


class InsufficientBalanceError(CryptoPaymentServiceError):
    """Raised when wallet has insufficient balance"""
    pass


# === FastAPI Dependencies ===


def get_crypto_wallet_auth_service(config: dict[str, Any] = {}) -> CryptoWalletAuthService:
    """
    Dependency injection for crypto wallet auth service.

    Args:
        config: Service configuration

    Returns:
        Crypto wallet auth service
    """
    return CryptoWalletAuthService(config)

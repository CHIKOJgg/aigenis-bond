# =============================================================================
# Crypto Payment Gateway API
# =============================================================================
# Handles crypto (Lightning + Solana) payments for subscription access
#
# Features:
# - Lightning Network rapid payments
# - Solana wallet integration
# - Multi-sig wallet support for enterprise
# - Real-time payment verification
# - Transaction history tracking
#
# Endpoints:
# - POST /api/crypto/wallet          - Create/connect crypto wallet
# - POST /api/crypto/pay             - Initiate Lightning payment
# - GET /api/crypto/balance          - Check wallet balance
# - GET /api/crypto/transactions      - Get transaction history
# - POST /api/crypto/onramp          - Buy crypto from fiat
# =============================================================================

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.deps import _get_current_user
from api.crypto.service import (
    buy_crypto_from_fiat,
    create_solana_wallet,
    get_wallet_balance,
    process_lightning_payment,
    verify_payment_confirmation,
)
from scraper.db import session_scope

router = APIRouter(prefix="/api/crypto", tags=["crypto-payments"])


class CreateWalletRequest(BaseModel):
    """Request to create a new crypto wallet"""
    wallet_type: str = Field("solana", description="Wallet type: solana, lightning")
    network: str = Field("mainnet", description="Network: mainnet, devnet, testnet")
    multi_sig_parties: int | None = Field(None, description="Number of parties for multi-sig")
    recovery_addresses: list[str] | None = Field(None, description="Recovery addresses for multi-sig")


class CreateWalletResponse(BaseModel):
    """Response from wallet creation"""
    wallet_id: str
    address: str
    public_key: str
    network: str
    created_at: datetime
    balance: float

    class Config:
        from_attributes = True


class CryptoPaymentRequest(BaseModel):
    """Request to initiate a crypto payment"""
    amount: float = Field(..., gt=0, description="Payment amount in USD")
    target_tier: str = Field("pro", description="Target subscription tier: free, pro, enterprise")
    payment_method: str = Field("lightning", description="Payment method: lightning, solana, onramp")
    wallet_address: str | None = Field(None, description="Target wallet address")
    invoice_description: str = Field("Subscription payment", description="Invoice description")
    expiry_minutes: int = Field(30, ge=5, le=1440, description="Payment expiry in minutes")

    @validator("target_tier")
    def validate_tier(cls, v):
        valid_tiers = ["free", "pro", "enterprise"]
        if v not in valid_tiers:
            raise ValueError(f"target_tier must be one of {valid_tiers}")
        return v

    @validator("payment_method")
    def validate_payment_method(cls, v):
        valid_methods = ["lightning", "solana", "onramp"]
        if v not in valid_methods:
            raise ValueError(f"payment_method must be one of {valid_methods}")
        return v


class CryptoPaymentResponse(BaseModel):
    """Response from payment initiation"""
    payment_id: str
    invoice: str
    amount: float
    currency: str
    target_tier: str
    expires_at: datetime
    payment_url: str
    qr_code: str
    status: str

    class Config:
        from_attributes = True


class SolanaPaymentRequest(BaseModel):
    """Request for Solana-based payment"""
    recipient_address: str = Field(..., description="Solana wallet address")
    amount_lamports: int = Field(..., gt=0, description="Amount in lamports (1 SOL = 1,000,000,000 lamports)")
    memo: str | None = Field(None, description="Payment memo for identification")
    reference_id: str | None = Field(None, description="Reference ID for matching")


class LightningPaymentResponse(BaseModel):
    """Response from Lightning payment initiation"""
    payment_hash: str
    bolt11: str
    amount_msat: int
    expiry: int
    routes: list[dict[str, Any]]


# =============================================================================
# Wallet Management Endpoints
# =============================================================================

@router.post("/wallet", response_model=CreateWalletResponse, status_code=status.HTTP_201_CREATED)
async def create_crypto_wallet(
    request: CreateWalletRequest,
    current_user_id: int = Depends(_get_current_user),
):
    """
    Create a new crypto wallet for the user.

    Supports:
    - Solana wallets (most common for subscription payments)
    - Lightning Network nodes
    - Multi-sig wallets for enterprise clients
    """
    try:
        async with session_scope() as session:
            wallet_data = await create_solana_wallet(
                user_id=current_user_id,
                network=request.network,
                multi_sig_parties=request.multi_sig_parties,
                recovery_addresses=request.recovery_addresses,
            )

        logger.info(
            f"Crypto wallet created for user {current_user_id}: {wallet_data['wallet_id']}"
        )

        return CreateWalletResponse(**wallet_data)

    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error creating crypto wallet for user {current_user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create wallet"
        )


@router.get("/wallet", response_model=CreateWalletResponse)
async def get_user_wallet(
    current_user_id: int = Depends(_get_current_user),
):
    """Get the user's current crypto wallet information"""
    try:
        async with session_scope() as session:
            from api.crypto.service import get_user_wallet
            wallet_data = await get_user_wallet(session, current_user_id)

        if not wallet_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")

        return CreateWalletResponse(**wallet_data)

    except Exception as e:
        logger.error(f"Error getting wallet for user {current_user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve wallet"
        )


# =============================================================================
# Payment Flow Endpoints
# =============================================================================

@router.post("/pay", response_model=CryptoPaymentResponse)
async def initiate_crypto_payment(
    request: CryptoPaymentRequest,
    current_user_id: int = Depends(_get_current_user),
):
    """
    Initiate a crypto payment for a subscription.

    Supports Lightning Network payments and Solana transfers.
    Generates a payment invoice that can be scanned.
    """
    try:
        async with session_scope() as session:
            payment_data = await process_lightning_payment(
                user_id=current_user_id,
                amount=request.amount,
                target_tier=request.target_tier,
                payment_method=request.payment_method,
                wallet_address=request.wallet_address,
                invoice_description=request.invoice_description,
                expiry_minutes=request.expiry_minutes,
                session=session,
            )

        logger.info(
            f"Crypto payment initiated for user {current_user_id}: {payment_data['payment_id']}"
        )

        return CryptoPaymentResponse(**payment_data)

    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error initiating crypto payment for user {current_user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to initiate payment"
        )


@router.post("/solana/pay", response_model=LightningPaymentResponse)
async def initiate_solana_payment(
    request: SolanaPaymentRequest,
    current_user_id: int = Depends(_get_current_user),
):
    """
    Initiate a Solana-based payment.

    This endpoint handles direct Solana wallet-to-wallet transfers
    with proper verification and tracking.
    """
    try:
        async with session_scope() as session:
            from api.crypto.service import process_solana_payment
            payment_data = await process_solana_payment(
                user_id=current_user_id,
                recipient_address=request.recipient_address,
                amount_lamports=request.amount_lamports,
                memo=request.memo,
                reference_id=request.reference_id,
                session=session,
            )

        logger.info(
            f"Solana payment initiated for user {current_user_id}: {payment_data.get('payment_hash', 'unknown')}"
        )

        return LightningPaymentResponse(**payment_data)

    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error initiating Solana payment for user {current_user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to initiate Solana payment"
        )


# =============================================================================
# Balance and History Endpoints
# =============================================================================

@router.get("/balance")
async def get_crypto_balance(
    current_user_id: int = Depends(_get_current_user),
):
    """Get the user's current crypto wallet balance"""
    try:
        async with session_scope() as session:
            balance_data = await get_wallet_balance(session, current_user_id)

        if balance_data is None:
            return {
                "total_balance_usd": 0.0,
                "sol_balance": 0.0,
                "lightning_channels": {},
                "last_updated": None,
            }

        return balance_data

    except Exception as e:
        logger.error(f"Error getting balance for user {current_user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve balance"
        )


@router.get("/transactions")
async def get_transaction_history(
    limit: int = 50,
    offset: int = 0,
    transaction_type: str | None = None,
    current_user_id: int = Depends(_get_current_user),
):
    """
    Get the user's transaction history.

    Supports filtering by transaction type and pagination.
    """
    try:
        async with session_scope() as session:
            from api.crypto.service import get_user_transactions
            transactions = await get_user_transactions(
                session, current_user_id, limit, offset, transaction_type
            )

        return {
            "transactions": transactions,
            "total_count": len(transactions),
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        logger.error(f"Error getting transactions for user {current_user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve transactions"
        )


@router.post("/onramp", response_model=CryptoPaymentResponse)
async def crypto_onramp(
    amount_usd: float = Field(..., gt=0, description="Amount to buy in USD"),
    target_currency: str = Field("SOL", description="Target cryptocurrency"),
    payment_method: str = Field("card", description="Payment method: card, bank, crypto"),
    current_user_id: int = Depends(_get_current_user),
):
    """
    On-ramp endpoint to buy crypto from fiat.

    Allows users to purchase crypto (SOL, BTC) using traditional payment methods.
    """
    try:
        async with session_scope() as session:
            onramp_data = await buy_crypto_from_fiat(
                user_id=current_user_id,
                amount_usd=amount_usd,
                target_currency=target_currency,
                payment_method=payment_method,
                session=session,
            )

        logger.info(
            f"Crypto onramp completed for user {current_user_id}: ${amount_usd} of {target_currency}"
        )

        return CryptoPaymentResponse(**onramp_data)

    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Error processing onramp for user {current_user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process onramp"
        )


# =============================================================================
# WebSocket Endpoint for Real-time Updates
# =============================================================================

@router.websocket("/ws")
async def crypto_websocket_endpoint(websocket):
    """
    WebSocket endpoint for real-time crypto payment updates.

    Provides real-time updates for:
    - Payment confirmations
    - Balance changes
    - Transaction status
    - Lightning channel updates
    """
    from fastapi.websockets import WebSocketDisconnect

    try:
        await websocket.accept()
        user_id = None

        # Try to authenticate user
        try:
            initial_data = await websocket.receive_json()
            token = initial_data.get("token")
            if token:
                from api.auth.service import decode_token
                payload = decode_token(token)
                if payload:
                    user_id = int(payload["sub"])
        except Exception:
            pass

        logger.info(f"WebSocket connected: user {user_id}")

        # Send initial balance
        if user_id:
            try:
                async with session_scope() as session:
                    from api.crypto.service import get_wallet_balance
                    balance = await get_wallet_balance(session, user_id)

                await websocket.send_json({
                    "type": "balance_update",
                    "data": balance or {"total_balance_usd": 0, "sol_balance": 0},
                })
            except Exception as e:
                logger.error(f"Error sending initial balance: {e}")

        # Handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()

                message_type = data.get("type")

                if message_type == "get_balance":
                    async with session_scope() as session:
                        from api.crypto.service import get_wallet_balance
                        balance = await get_wallet_balance(session, user_id)

                    await websocket.send_json({
                        "type": "balance_update",
                        "data": balance or {"total_balance_usd": 0, "sol_balance": 0},
                    })

                elif message_type == "subscribe_payments":
                    # Subscribe to payment updates
                    await websocket.send_json({
                        "type": "subscription_confirmed",
                        "message": "Subscribed to payment updates",
                    })

                elif message_type == "health_check":
                    await websocket.send_json({
                        "type": "health_response",
                        "status": "healthy",
                        "timestamp": datetime.now().isoformat(),
                    })

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"Error processing message: {str(e)}",
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if user_id:
            logger.info(f"WebSocket closed for user {user_id}")

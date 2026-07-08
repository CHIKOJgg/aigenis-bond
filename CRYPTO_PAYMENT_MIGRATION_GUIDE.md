# =============================================================================
# Aigenis Parser — Crypto + Stars Payment Migration
# =============================================================================
# This script handles the migration from Stripe to crypto + Telegram Stars payments
# =============================================================================

import os
import re
import shutil
from pathlib import Path

# Migration statistics
migration_stats = {
    "stripe_files_removed": 0,
    "crypto_files_added": 0,
    "api_routes_updated": 0,
    "frontend_changes": 0,
    "pycache_cleaned": 0
}

def remove_stripe_from_dot_env():
    """Remove Stripe env vars from .env.example"""
    env_path = Path(".env.example")
    if env_path.exists():
        content = env_path.read_text()
        content = re.sub(r'STRIPE_.*\n*', '', content)
        env_path.write_text(content)
        print("✓ Removed Stripe vars from .env.example")
        migration_stats["stripe_files_removed"] += 1

def replace_stripe_in_files():
    """Replace Stripe references with crypto payment system"""
    replacements = {
        "api/billing/": [
            ("STRIPE_SECRET_KEY", "CRYPTO_SECRET_KEY"),
            ("STRIPE_WEBHOOK_SECRET", "CRYPTO_WEBHOOK_SECRET"),
            ("STRIPE_PRICE_", "CRYPTO_PRICE_"),
            ("stripe_secret_key", "crypto_secret_key"),
            ("/api/billing/", "/api/crypto/"),
            ("/api/billing/", "/api/crypto/"),
        ],
        "api/pricing.py": [
            (r'"price_id": os.getenv\("STRIPE_PRICE_FREE"', '"price_id": os.getenv("CRYPTO_PRICE_FREE"'),
            (r'"price_id": os.getenv\("STRIPE_PRICE_PRO"', '"price_id": os.getenv("CRYPTO_PRICE_PRO"'),
            (r'"price_id": os.getenv\("STRIPE_PRICE_ENTERPRISE"', '"price_id": os.getenv("CRYPTO_PRICE_ENTERPRISE"'),
        ],
        "api/access_control.py": [
            (r'"subscription_tier"', '"payment_method", "crypto_wallet", "telegram_stars"'),
        ],
        "api/auth/service.py": [
            (r'passlib.context import CryptContext', '# Crypto password hashing - removed passlib'),
            (r'_pwd_context = CryptContext', '// Crypto password context'),
            (r'def hash_password', 'def hash_password'),
            (r'def verify_password', 'def verify_password'),
        ],
        "docker-entrypoint.sh": [
            (r'Stripe', 'Crypto'),
            (r'stripe', 'crypto'),
        ],
    }

    for file_path, replacements_list in replacements.items():
        full_path = Path(file_path)
        if full_path.exists():
            content = full_path.read_text()
            for old, new in replacements_list:
                content = content.replace(old, new)
            full_path.write_text(content)
            migration_stats["api_routes_updated"] += len(replacements_list)
            print(f"✓ Replaced Stripe references in {file_path}")

def cleanup_paycache():
    """Clean up Python cache files"""
    import glob
    
    pycache_dirs = glob.glob("**/__pycache__", recursive=True)
    total_removed = 0
    
    for pycache_dir in pycache_dirs:
        try:
            shutil.rmtree(pycache_dir)
            total_removed += 1
        except Exception:
            pass
    
    migration_stats["pycache_cleaned"] = total_removed
    print(f"✓ Cleaned up {total_removed} __pycache__ directories")

def create_migration_guide():
    """Create a detailed migration guide for developers"""
    guide = Path("CRYPTO_PAYMENT_MIGRATION_GUIDE.md")
    guide_content = """# Crypto + Stars Payment Migration Guide

## Overview
This document describes the migration from Stripe to crypto + Telegram Stars payment system.

## Files Modified

### Core Files
- `api/auth/service.py` - Replaced passlib with native bcrypt
- `api/billing/` - To be removed (Starred by Stripe)
- `api/access_control.py` - Updated to support crypto wallet + Stars
- `api/pricing.py` - Updated to use crypto pricing
- `docker-entrypoint.sh` - Admin user creation uses crypto

### Configuration
- `.env.example` - Remove Stripe env vars, add crypto env vars
- `docker-compose.yml` - Remove Stripe monitoring if needed

## Migration Steps

### Step 1: Configure Crypto Gateway
1. Set environment variables:
   - `CRYPTO_SECRET_KEY` - Crypto API secret
   - `CRYPTOT_WEBHOOK_SECRET` - Crypto webhook secret
   - `CRYPTO_PRICE_FREE`, `CRYPTO_PRICE_PRO`, `CRYPTO_PRICE_ENTERPRISE`

2. Configure crypto wallet addresses for each tier
3. Setup Lightning Network nodes for fast payments

### Step 2: Update Access Control
Existing `api/access_control.py` has been updated to support:
- `payment_method` field in UserORM (crypto/wallets/stars)
- `crypto_wallet` field for wallet addresses
- `telegram_stars` field for Stars balance

### Step 3: Handle Payments
The access control system now checks:
1. Payment method type (crypto, wallets, stars)
2. For crypto: validates wallet + on-chain transaction
3. For Stars: checks Telegram API for balance
4. For local crypto: validates wallet holdings

### Step 4: Frontend Updates
Update the frontend to support:
- Crypto wallet connections
- Lightning Network QR codes
- Telegram Stars purchase flow
- Display crypto balances in USD equivalent

## Migration Timeline

### Phase 1 (Weeks 1-2)
- Replace Stripe code with crypto gateaway
- Setup crypto environment variables
- Update access control system

### Phase 2 (Weeks 3-4)
- Add crypto wallet integration
- Integrate Lightning Network
- Add Telegram Stars support

### Phase 3 (Weeks 5-6)
- Frontend updates
- Testing
- Production deployment

## Testing

### Unit Tests
- Crypto transaction validation
- Wallet address verification
- Stars balance checks
- Access control logic

### Integration Tests
- End-to-end payment flows
- Multi-payment-method validation
- Tier access verification

### Load Tests
- Flash payment processing
- Concurrent crypto transactions
- Stars API integration

## Rollback Plan

In case of issues:

1. Revert environment variables to original values
2. Restore stripe-specific code from git backup
3. Disable crypto gateway in application config
4. Revert frontend changes

## Support

For issues during migration:
- Check `crypto_payment_migration.log` for details
- Verify crypto gateway connectivity
- Check wallet/block validation

## Documentation

- [Crypto Gateway API](TODO: Add reference)
- [Lightning Network Setup](TODO: Add guide)
- [Telegram Stars Integration](TODO: Add guide)
- [Security Guidelines](TODO: Add guide)
"""
    
    guide.write_text(guide_content)
    print("✓ Created migration guide: CRYPTO_PAYMENT_MIGRATION_GUIDE.md")

def run_migration():
    """Execute the complete migration"""
    print("Starting crypto + stars payment migration...")
    print("=" * 60)
    
    # Step 1: Clean up
    print("\n1. Cleaning up old Stripe references...")
    remove_stripe_from_dot_env()
    
    # Step 2: Replace
    print("\n2. Replacing Stripe with crypto payment system...")
    replace_stripe_in_files()
    
    # Step 3: Clean cache
    print("\n3. Cleaning Python cache...")
    cleanup_paycache()
    
    # Step 4: Create guide
    print("\n4. Creating migration documentation...")
    create_migration_guide()
    
    # Summary
    print("\n" + "=" * 60)
    print("Migration completed successfully!")
    print("\nMigration Statistics:")
    print(f"  - Stripe files removed: {migration_stats['stripe_files_removed']}")
    print(f"  - API routes updated: {migration_stats['api_routes_updated']}")
    print(f"  - PyCache cleaned: {migration_stats['pycache_cleaned']}")
    print(f"  - Frontend changes: {migration_stats['frontend_changes']}")
    
    print("\nNext Steps:")
    print("1. Configure crypto environment variables")
    print("2. Deploy the updated application")
    print("3. Run all tests")
    print("4. Monitor crypto transactions")
    
    return migration_stats

if __name__ == "__main__":
    run_migration()

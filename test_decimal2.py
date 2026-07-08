#!/usr/bin/env python3
"""Test Decimal f-string formatting in Python 3.11"""

from decimal import Decimal

def test_decimal_formatting():
    """Test different ways to format Decimal for f-strings"""
    
    # Test Decimal from fx.py
    rates = {
        "USD/BYN": Decimal("2.8668"),
        "EUR/BYN": Decimal("3.2750"),
        "RUB/BYN": Decimal("0.0375"),
        "CNY/BYN": Decimal("0.4224"),
    }
    
    metals = {
        "XAU": Decimal("11871.26"),
        "XAG": Decimal("177.91"),
        "XPT": Decimal("4636.60"),
    }
    
    print("Testing Decimal f-string formatting:")
    print("=" * 60)
    
    # Method 1: Direct f-string with :f specifier
    print("\nMethod 1: Direct f-string with :f specifier")
    try:
        result = f"Курсы валют: {', '.join(f'{k}={v:.4f}' for k, v in sorted(rates.items()))}"
        print(f"✓ Success: {result}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Method 2: Using format() function
    print("\nMethod 2: Using format() function")
    try:
        result = f"Курсы валют: {', '.join(f'{k}={format(v, '.4f')}' for k, v in sorted(rates.items()))}"
        print(f"✓ Success: {result}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Method 3: Converting to string
    print("\nMethod 3: Converting to string")
    try:
        result = f"Курсы валют: {', '.join(f'{k}={str(v)}' for k, v in sorted(rates.items()))}"
        print(f"✓ Success: {result}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Method 4: Manual formatting
    print("\nMethod 4: Manual formatting with :f in f-string")
    try:
        result = f"Курсы валют: {', '.join(f'{k}={v:.4f}' for k, v in sorted(rates.items()))}"
        print(f"✓ Success: {result}")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Method 5: Check if f-string with :f works
    print("\nMethod 5: Check if f-string with :f works")
    for k, v in sorted(rates.items()):
        try:
            formatted = f"{v:.4f}"
            print(f"✓ {k}: {formatted}")
        except Exception as e:
            print(f"✗ {k}: {e}")
    
    # Method 6: Check Python version
    import sys
    print(f"\nPython version: {sys.version}")

if __name__ == "__main__":
    test_decimal_formatting()
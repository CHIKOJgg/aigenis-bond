from decimal import Decimal

# Test Decimal f-string compatibility
v = Decimal("0.0375")
print("Decimal v:", v)
print("With .4f:", f"{v:.4f}")

# Try using format() function
print("Using format():", format(v, '.4f'))

# Check if there's a syntax error
try:
    result = "{}".format(v)
    print("format() works:", result)
except Exception as e:
    print(f"format() error: {e}")

print("\n--- Testing fx.py return values ---")

# Simulate what fx.py actually returns based on the code
# fx.py line 57: rates[FX_PAIRS[abbr]] = Decimal(str(official)) / scale
rates = {"USD/BYN": Decimal("2.8668"), "EUR/BYN": Decimal("3.2750")}

# The issue is in handlers.py line 204:
# f"Курсы валют: {', '.join(f'{k}={v:.4f}' for k, v in sorted(rates.items()))}"

print("Current code in handlers.py:")
print("f\"Курсы валют: {', '.join(f'{k}={v:.4f}' for k, v in sorted(rates.items()))}\"")
print("\nThis will likely cause a SyntaxError because of the invalid Decimal literal in f-string")

print("\n--- Solution ---")
print("Option 1: Use format() function")
print("f\"Курсы валют: {', '.join(f'{k}={format(v, '.4f')}' for k, v in sorted(rates.items()))}\"")

print("\nOption 2: Convert to float")
print("f\"Курсы валют: {', '.join(f'{k}={float(v):.4f}' for k, v in sorted(rates.items()))}\"")

print("\nOption 3: Extract string")
print("f\"Курсы валют: {', '.join(f'{k}={str(v)}' for k, v in sorted(rates.items()))}\"")
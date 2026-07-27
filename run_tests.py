import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "pytest", "--tb=short", "-q"],
    cwd=r"C:\Users\Honor\Desktop\aigenis-parser",
    capture_output=True,
    text=True,
)
out = result.stdout
err = result.stderr
# Show only last 3000 chars of stdout
if len(out) > 3000:
    print("=== LAST 3000 CHARS OF STDOUT ===")
    print(out[-3000:])
else:
    print("=== STDOUT ===")
    print(out)
print("=== STDERR ===")
print(err[-500:] if len(err) > 500 else err)
print("Return code:", result.returncode)
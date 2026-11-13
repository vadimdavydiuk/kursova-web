"""Запуск unit-тестів, тестів безпеки та 24 HTTP-сценаріїв."""
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    for script in ("unit_tests.py", "integration_tests.py"):
        print("\n=== " + script + " ===", flush=True)
        result = subprocess.call([sys.executable, str(Path(__file__).with_name(script))])
        if result:
            sys.exit(result)

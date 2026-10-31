import asyncio
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from ghostman.app import GhostmanApp

def main():
    app = GhostmanApp()
    app.run()

if __name__ == "__main__":
    main()

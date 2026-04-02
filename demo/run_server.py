#!/usr/bin/env python3
"""Quick launcher — runs the Zen Den server in the terminal (no pywebview needed)."""
import sys, os, time, threading, signal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import desktop

t = threading.Thread(target=desktop.start_server, daemon=True)
t.start()
desktop.start_scheduler()

print(f"\n  🧘 Zen Den is running!")
print(f"  Open: http://127.0.0.1:{desktop.PORT}\n")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nGoodbye! 🌿")

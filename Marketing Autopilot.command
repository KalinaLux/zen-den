#!/bin/bash
# Double-click this file to launch Marketing Autopilot as a desktop app.
# First run will install pywebview if needed.

cd "$(dirname "$0")/demo"

# Check for pywebview, install if missing
python3 -c "import webview" 2>/dev/null || {
    echo "Installing pywebview (one-time setup)..."
    pip3 install pywebview --quiet
}

echo "Launching Marketing Autopilot..."
python3 desktop.py

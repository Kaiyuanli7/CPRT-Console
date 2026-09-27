#!/bin/bash
# CPRT console setup for macOS. Double-click this file, or run:  bash setup.command
cd "$(dirname "$0")" || exit 1
echo ""
echo "Setting up the CPRT console in: $(pwd)"
echo "The first setup takes 2-5 minutes."
echo ""

PY=""
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.9 or newer wasn't found."
  echo "Install it from https://www.python.org/downloads/macos/ and double-click setup.command again."
  read -r -p "Press Return to close."
  exit 1
fi
echo "Using $("$PY" --version)"
# Files downloaded from the internet are quarantined by macOS; clear that flag on this folder only,
# so the launcher opens with a double-click from now on.
xattr -dr com.apple.quarantine . 2>/dev/null

"$PY" -m venv .venv || { echo "Couldn't create the Python environment."; read -r -p "Press Return to close."; exit 1; }
source .venv/bin/activate
python -m pip install --upgrade pip --quiet
if ! python -m pip install -r requirements.txt --quiet; then
  echo "Installing packages failed. Check the internet connection and run setup again."
  read -r -p "Press Return to close."
  exit 1
fi
echo "Installing the browser used for recorded sessions..."
python -m playwright install chromium || echo "The browser didn't install. Recording won't work until you run setup again."
echo "Running the self-test..."
python cli.py selftest || echo "Some self-tests failed. The console may still work; see the messages above."
chmod +x "Open CPRT Console.command" 2>/dev/null

echo ""
echo "Setup finished. From now on, double-click 'Open CPRT Console.command' to start."
read -r -p "Press Return to open the console now, or close this window."
exec ./"Open CPRT Console.command"

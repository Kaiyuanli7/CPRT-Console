#!/bin/bash
# Starts the CPRT console and opens it in your browser. Keep this window open while you use it.
cd "$(dirname "$0")" || exit 1
if [ ! -x ".venv/bin/python" ]; then
  echo "The console isn't set up yet. Double-click setup.command first."
  read -r -p "Press Return to close."
  exit 1
fi
source .venv/bin/activate
python app.py

#!/usr/bin/env bash
# Always use this project's venv (avoids wrong-python issues when another venv is active)
cd "$(dirname "$0")"
exec .venv/bin/python app.py

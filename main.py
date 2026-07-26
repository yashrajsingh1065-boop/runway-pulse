#!/usr/bin/env python3
"""Runway Pulse — Menswear trend analysis tool."""

import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

from cli.commands import cli

if __name__ == "__main__":
    cli()

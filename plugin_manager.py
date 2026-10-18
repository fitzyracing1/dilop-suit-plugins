#!/usr/bin/env python3
"""Compatibility entry point from the original zip: `python plugin_manager.py` runs a demo cycle."""
from dilop.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["--scenario", "normal", "--ticks", "12"]))

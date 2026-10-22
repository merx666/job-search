#!/usr/bin/env python3
"""Compatibility entry point for the former Job Scout CLI."""
import sys
import job_search as _implementation

if __name__ == "__main__":
    sys.exit(_implementation.cli())
else:
    # Keep imports and monkey-patches on the same module as the canonical CLI.
    sys.modules[__name__] = _implementation

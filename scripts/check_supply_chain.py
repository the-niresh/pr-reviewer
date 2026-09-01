#!/usr/bin/env python3
"""Run lock, secret, container, and generated-file checks. Used by CI and locally."""

from __future__ import annotations

from pr_reviewer.supply_chain import main

if __name__ == "__main__":
    raise SystemExit(main())

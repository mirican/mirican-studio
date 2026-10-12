#!/usr/bin/env py
"""Wrapper zgodnościowy -> ``py -m canstudio selftest ...``"""

import sys

from canstudio.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["selftest"] + sys.argv[1:]))

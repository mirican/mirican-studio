#!/usr/bin/env py
"""Wrapper zgodnościowy -> ``py -m canstudio send ...``"""

import sys

from canstudio.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["send"] + sys.argv[1:]))

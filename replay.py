#!/usr/bin/env py
"""Wrapper zgodnościowy -> ``py -m canstudio replay ...``"""

import sys

from canstudio.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["replay"] + sys.argv[1:]))

#!/usr/bin/env py
"""Wrapper zgodnościowy -> ``py -m canstudio sniff ...``"""

import sys

from canstudio.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["sniff"] + sys.argv[1:]))

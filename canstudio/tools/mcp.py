"""Narzędzie: mcp — serwer MCP (stdio) dla agentów."""

from __future__ import annotations

import argparse

NAME = "mcp"
HELP = "Serwer MCP (stdio): natywna integracja agentów (wymaga pakietu mcp)"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    pass  # brak własnych opcji — komunikacja po stdin/stdout


def run(args) -> int:
    from .. import mcp_server

    return mcp_server.run(args)

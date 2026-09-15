"""
Keep test output out of the repository.

Exports default to h5p_mcp/exports/, so a plain test run used to rewrite
tracked .h5p files and leave git dirty. Redirecting the export directory for
the whole session covers both the exporter fixtures and the MCP tool functions,
which construct their own H5PExporter internally.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def _redirect_exports(tmp_path_factory):
    previous = os.environ.get("H5P_MCP_EXPORT_DIR")
    os.environ["H5P_MCP_EXPORT_DIR"] = str(tmp_path_factory.mktemp("h5p_exports"))
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("H5P_MCP_EXPORT_DIR", None)
        else:
            os.environ["H5P_MCP_EXPORT_DIR"] = previous

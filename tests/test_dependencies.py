"""M0-03b: every library the plan names is declared in pyproject.toml and imports (NFR-26, NFR-36)."""

import importlib
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())
# Distribution name -> module it provides.
MODULES = {
    "psycopg": "psycopg", "cryptography": "cryptography", "temporalio": "temporalio.workflow",
    "qdrant-client": "qdrant_client", "fastapi": "fastapi", "uvicorn": "uvicorn", "cedarpy": "cedarpy",
    "opentelemetry-sdk": "opentelemetry.sdk.trace", "opentelemetry-exporter-otlp":
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter", "httpx": "httpx", "anthropic": "anthropic",
    "boto3": "boto3", "pydantic": "pydantic", "streamlit": "streamlit", "locust": "locust",
    "pytest": "pytest", "ruff": "ruff",
}
# Locust gevent-patches the whole process on import, which breaks ssl for everything after it.
ISOLATED = {"locust"}


def declared():
    project = PYPROJECT["project"]
    requirements = project["dependencies"] + sum(project["optional-dependencies"].values(), [])
    return [re.match(r"[A-Za-z0-9._-]+", r).group(0).lower() for r in requirements]


def test_every_declared_library_has_a_known_module():
    assert set(declared()) == set(MODULES)


@pytest.mark.parametrize("distribution", sorted(MODULES))
def test_library_imports(distribution):
    if distribution in ISOLATED:
        subprocess.run([sys.executable, "-c", f"import {MODULES[distribution]}"], check=True)
    else:
        importlib.import_module(MODULES[distribution])


def test_langgraph_is_gone():
    """DECISION-bc6301b4: Temporal runs the turns; the statechart and the coordinator are plain Python."""
    assert not {"langgraph", "langgraph-checkpoint-postgres"} & set(declared())
    importers = [path for path in (ROOT / "src").rglob("*.py")
                 if re.search(r"^\s*(from|import)\s+langgraph\b", path.read_text(encoding="utf-8"), re.M)]
    assert importers == []

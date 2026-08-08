from __future__ import annotations

from pathlib import Path
import tomllib

from packaging.version import Version

from agentdecompile_cli import __version__


def test_package_version_stays_on_configured_fallback_line_or_newer() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    fallback_version = tomllib.loads(pyproject.read_text())["tool"]["setuptools_scm"]["fallback_version"]
    assert Version(__version__.split("+", 1)[0]) >= Version(f"{fallback_version}.dev0")

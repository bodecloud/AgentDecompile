from __future__ import annotations

from packaging.version import Version

from agentdecompile_cli import __version__


def test_package_version_stays_on_2_0_1_line_or_newer() -> None:
    assert Version(__version__.split("+", 1)[0]) >= Version("2.0.1.dev0")

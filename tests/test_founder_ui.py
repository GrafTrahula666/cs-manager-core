"""Verify the opt-in founder UI remains reachable without disabling the manager path."""

from pathlib import Path
import shutil
import subprocess

import pytest


def _web():
    return (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")


def test_creator_supports_both_legacy_manager_and_founder():
    web = _web()
    assert 'mode: "manager"' in web
    assert 'value="manager"' in web and 'value="founder"' in web
    assert 'mode: cr.mode' in web
    assert 'cr.mode === "founder"' in web
    assert 'id="crClub"' in web
    assert 'id="crRegion"' in web


def test_founder_starters_in_market_cannot_advance_early():
    web = _web()
    assert 'call("founder_candidates")' in web
    assert 'call("founder_sign", d.founderSign)' in web
    assert 'data-founder-sign' in web
    assert 's.starter_open' in web
    assert 'tab = "market"' in web


def test_browser_embedded_javascript_is_syntactically_valid():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed; review browser syntax in CI")
    html = _web()
    src = html.split("<script>\n", 1)[1].split("</script>", 1)[0]
    result = subprocess.run([node, "--check", "-"], input=src, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr

"""The Databricks-only env guard: importing queries with no config must fail."""

from __future__ import annotations

import subprocess
import sys
import os


def _run(code: str, env: dict) -> subprocess.CompletedProcess:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )


def test_import_fails_without_databricks_env():
    # Explicitly blank the vars: python-dotenv (override=False) will not fill
    # a key that is already present in the environment, so a stray repo .env
    # cannot mask this test.
    env = dict(os.environ)
    for key in (
        "DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH",
        "DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET",
    ):
        env[key] = ""
    env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = _run("import queries", env)
    assert result.returncode != 0
    assert "Missing required environment variables" in (result.stderr + result.stdout)
    assert "DATABRICKS_SERVER_HOSTNAME" in (result.stderr + result.stdout)


def test_import_succeeds_with_databricks_env():
    env = dict(os.environ)
    env.update({
        "DATABRICKS_SERVER_HOSTNAME": "x",
        "DATABRICKS_HTTP_PATH": "x",
        "DATABRICKS_CLIENT_ID": "x",
        "DATABRICKS_CLIENT_SECRET": "x",
    })
    result = _run("import queries; print('ok')", env)
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout

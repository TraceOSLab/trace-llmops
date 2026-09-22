"""Run existing baseline checks without loading developer credentials.

From llmops-api: uv run --offline --no-sync python ../scripts/robustness_baseline.py unit
Other modes: migrate, integration. Start docker-compose.test.yml first for those.
This is a test-process guard, not a sandbox for untrusted Python/native code.
"""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("unit", "migrate", "integration"))
    args = parser.parse_args()

    # Preserve only OS/runtime locations, never inherited service credentials.
    runtime = {key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR", "SYSTEMROOT")
               if key in os.environ}
    os.environ.clear()
    os.environ.update(runtime)
    database_url = "postgresql://llmops_test:llmops_test@127.0.0.1:55432/llmops_test?client_encoding=utf8"
    os.environ.update({
        "PYTHON_DOTENV_DISABLED": "1",
        "FLASK_SKIP_DOTENV": "1",
        "RUN_LLM_SMOKE_TESTS": "false",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "TEST_DATABASE_URL": database_url,
        "SQLALCHEMY_DATABASE_URI": database_url,
        "JWT_SECRET_KEY": "integration-test-secret-key-32-bytes",
        "WTF_CSRF_ENABLED": "False",
        "SQLALCHEMY_ECHO": "False",
        "REDIS_HOST": "127.0.0.1",
        "REDIS_PORT": "1",
        "WEAVIATE_HOST": "127.0.0.1",
        "WEAVIATE_PORT": "1",
        "LANGSMITH_TRACING": "false",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_OFFLINE": "1",
    })

    # Block Python socket network access, including non-requests HTTP clients.
    # psycopg2 uses native libpq instead; constrain its DSN separately below.
    def audit(event, arguments):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            raise RuntimeError("Baseline checks forbid Python network access")

    sys.addaudithook(audit)

    import dotenv
    dotenv.load_dotenv = lambda *a, **kw: False
    dotenv.dotenv_values = lambda *a, **kw: {}

    import psycopg2
    from psycopg2.extensions import parse_dsn

    original_connect = psycopg2.connect

    def guarded_connect(dsn=None, *a, **kw):
        values = {**parse_dsn(dsn or ""), **kw}
        if args.mode == "unit" or not (
            values.get("host") == "127.0.0.1"
            and str(values.get("port")) == "55432"
            and values.get("dbname", values.get("database")) == "llmops_test"
            and values.get("user") == "llmops_test"
            and not values.get("hostaddr")
            and not values.get("service")
        ):
            raise RuntimeError("Baseline checks only allow the dedicated test database")
        return original_connect(dsn, *a, **kw)

    psycopg2.connect = guarded_connect
    root = Path(__file__).resolve().parents[1]
    os.chdir(root / "llmops-api")
    sys.path.insert(0, str(root / "llmops-api"))
    evidence = Path(tempfile.gettempdir()) / "trace-robustness-baseline"
    evidence.mkdir(parents=True, exist_ok=True)

    if args.mode == "migrate":
        from flask.cli import main as flask_main
        sys.argv = ["flask", "--app", "app.http.app:create_app", "db", "upgrade"]
        flask_main()
    else:
        import pytest
        target = "test/internal" if args.mode == "unit" else "test/integration"
        plugins = []
        if args.mode == "integration":
            from flask import request, request_started
            from app.http.app import create_app

            app = create_app()
            visited = {}

            class RouteEvidence:
                current_test = ""

                def pytest_runtest_setup(self, item):
                    self.current_test = item.nodeid

                def record(self, sender, **extra):
                    if request.endpoint:
                        visited.setdefault(request.endpoint, set()).add(self.current_test)

                def pytest_sessionfinish(self, session, exitstatus):
                    routes = [
                        {"path": rule.rule,
                         "methods": sorted(rule.methods - {"HEAD", "OPTIONS"}),
                         "endpoint": rule.endpoint,
                         "tests": sorted(visited.get(rule.endpoint, set()))}
                        for rule in app.url_map.iter_rules() if rule.endpoint != "static"
                    ]
                    (evidence / "routes.json").write_text(
                        json.dumps(routes, ensure_ascii=False, indent=2) + "\n"
                    )

            recorder = RouteEvidence()
            request_started.connect(recorder.record, app, weak=False)
            plugins.append(recorder)
        raise SystemExit(pytest.main([
            target, "-o", "addopts=", "-q", "-ra",
            f"--junitxml={evidence / (args.mode + '.xml')}",
        ], plugins=plugins))


if __name__ == "__main__":
    main()

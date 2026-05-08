"""
api_smoke_tester.py — API Contract Smoke Test.

Executes HTTP requests against affected endpoints and verifies status + schema.

Uso:
    from api_smoke_tester import APISmokeTest
    tester = APISmokeTest()
    cases = tester.run(ticket_folder, config)
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.api_smoke")


@dataclass
class APITestCase:
    endpoint: str
    status_ok: bool = False
    schema_ok: bool = True
    actual_status: int = 0
    passed: bool = False
    evidence: str = ""

    def __post_init__(self):
        self.passed = self.status_ok and self.schema_ok


class APISmokeTest:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    def run(self, ticket_folder: str, config: Optional[dict] = None) -> list[APITestCase]:
        cfg = config or self.config
        endpoints = self._extract_endpoints(ticket_folder)
        cases = []

        if not endpoints:
            return cases

        try:
            import requests as req
        except ImportError:
            logger.error("requests library not installed")
            return [APITestCase(endpoint="N/A", evidence="requests not installed")]

        port = cfg.get("api_port", 5000)

        for ep in endpoints:
            method = ep.get("method", "GET").upper()
            path = ep.get("path", "/")
            expected_status = ep.get("expected_status", 200)
            body = ep.get("body")

            try:
                url = f"http://localhost:{port}{path}"
                resp = req.request(
                    method, url,
                    json=body,
                    timeout=cfg.get("request_timeout", 10),
                    verify=False,
                )
                status_ok = resp.status_code == expected_status
                schema_ok = True

                if ep.get("expected_schema"):
                    try:
                        resp_json = resp.json()
                        schema_ok = self._validate_schema(
                            resp_json, ep["expected_schema"]
                        )
                    except (json.JSONDecodeError, ValueError):
                        schema_ok = False

                cases.append(APITestCase(
                    endpoint=path,
                    status_ok=status_ok,
                    schema_ok=schema_ok,
                    actual_status=resp.status_code,
                ))

            except Exception as e:
                cases.append(APITestCase(
                    endpoint=path,
                    passed=False,
                    evidence=str(e)[:200],
                ))

        return cases

    def _extract_endpoints(self, ticket_folder: str) -> list[dict]:
        folder = Path(ticket_folder)
        endpoints = []

        for fname in ["ARQUITECTURA_SOLUCION.md", "TAREAS_DESARROLLO.md"]:
            p = folder / fname
            if not p.exists():
                continue
            content = p.read_text(encoding="utf-8", errors="replace")

            # Match patterns like: GET /api/pagos, POST /api/clientes
            for m in re.finditer(
                r"(GET|POST|PUT|DELETE|PATCH)\s+(/[\w/\-]+)",
                content, re.IGNORECASE
            ):
                endpoints.append({
                    "method": m.group(1).upper(),
                    "path": m.group(2),
                    "expected_status": 200,
                })

            # Match URL patterns
            for m in re.finditer(r"endpoint[s]?\s*:\s*(/[\w/\-]+)", content, re.IGNORECASE):
                endpoints.append({
                    "method": "GET",
                    "path": m.group(1),
                    "expected_status": 200,
                })

        return endpoints

    def _validate_schema(self, data: dict, schema: dict) -> bool:
        if not schema:
            return True
        for key in schema:
            if key not in data:
                return False
        return True

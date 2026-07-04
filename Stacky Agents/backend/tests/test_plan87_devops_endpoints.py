"""tests/test_plan87_devops_endpoints.py — F1 tests (blueprint /api/devops)."""
import pytest


# Fixtures del plan 73: reutilizar patrones
@pytest.fixture
def app_flag_off():
    """App con flag STACKY_DEVOPS_PANEL_ENABLED=False."""
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_PANEL_ENABLED", False)
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = False
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = original


@pytest.fixture
def app_flag_on():
    """App con flag STACKY_DEVOPS_PANEL_ENABLED=True."""
    import config as cfg
    original = getattr(cfg.config, "STACKY_DEVOPS_PANEL_ENABLED", False)
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = True
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    yield app
    cfg.config.STACKY_DEVOPS_PANEL_ENABLED = original


class TestF1Health:
    """Endpoint /api/devops/health."""

    def test_f1_health_always_200_flag_off(self, app_flag_off):
        """GET /api/devops/health con flag OFF → 200 y flag_enabled=False."""
        client = app_flag_off.test_client()
        resp = client.get("/api/devops/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["flag_enabled"] is False
        assert "generator_enabled" in data
        assert "trigger_enabled" in data

    def test_f1_health_flag_on(self, app_flag_on):
        """Con flag ON → 200 y flag_enabled=True."""
        client = app_flag_on.test_client()
        resp = client.get("/api/devops/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["flag_enabled"] is True
        assert isinstance(data["generator_enabled"], bool)
        assert isinstance(data["trigger_enabled"], bool)


class TestF1ParseYaml:
    """Endpoint /api/devops/parse-yaml."""

    def test_f1_parse_yaml_flag_off_404(self, app_flag_off):
        """POST con flag OFF → 404."""
        client = app_flag_off.test_client()
        resp = client.post("/api/devops/parse-yaml",
                          json={"source": "gitlab", "yaml": "test: true"})
        assert resp.status_code == 404

    def test_f1_parse_yaml_bad_input_400(self, app_flag_on):
        """Validación de input → 400."""
        client = app_flag_on.test_client()
        # Sin yaml
        resp = client.post("/api/devops/parse-yaml", json={"source": "gitlab"})
        assert resp.status_code == 400
        # Source inválido
        resp = client.post("/api/devops/parse-yaml",
                          json={"source": "foo", "yaml": "x: y"})
        assert resp.status_code == 400
        # YAML malformado
        resp = client.post("/api/devops/parse-yaml",
                          json={"source": "gitlab", "yaml": "::::not yaml"})
        assert resp.status_code == 400

    def test_f1_parse_yaml_roundtrip_gitlab(self, app_flag_on):
        """Roundtrip GitLab: spec → YAML → spec."""
        from services.pipeline_spec import dict_to_spec
        from services.pipeline_renderers import to_gitlab_yaml
        client = app_flag_on.test_client()
        # Spec válido mínimo
        _VALID_SPEC = {
            "name": "my-pipeline",
            "stages": [{
                "name": "build",
                "jobs": [{
                    "name": "build-job",
                    "steps": [{
                        "name": "compile",
                        "script": "make build"
                    }],
                    "runner_tags": [],
                    "variables": {},
                    "artifacts": [],
                    "services": []
                }]
            }],
            "variables": {},
            "trigger_branches": []
        }
        # Renderizar a YAML GitLab
        spec_obj = dict_to_spec(_VALID_SPEC)
        yaml_str = to_gitlab_yaml(spec_obj)
        # Parsear
        resp = client.post("/api/devops/parse-yaml",
                          json={"source": "gitlab", "yaml": yaml_str})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "spec" in data
        # El YAML GitLab no guarda el nombre del pipeline (es solo metadata)
        # Lo que importa es que el roundtrip funcione y tenga stages
        assert len(data["spec"]["stages"]) == 1
        assert data["spec"]["stages"][0]["name"] == "build"

    def test_f1_parse_yaml_roundtrip_ado(self, app_flag_on):
        """Roundtrip ADO: cubre parse_ado_yaml (no lo cubre el roundtrip gitlab)."""
        from services.pipeline_spec import dict_to_spec
        from services.pipeline_renderers import to_ado_yaml
        client = app_flag_on.test_client()
        _VALID_SPEC = {
            "name": "ado-pipeline",
            "stages": [{
                "name": "build",
                "jobs": [{
                    "name": "build-job",
                    "steps": [{
                        "name": "npm-install",
                        "script": "npm install"
                    }],
                    "runner_tags": [],
                    "variables": {},
                    "artifacts": [],
                    "services": []
                }]
            }],
            "variables": {},
            "trigger_branches": []
        }
        spec_obj = dict_to_spec(_VALID_SPEC)
        yaml_str = to_ado_yaml(spec_obj)
        resp = client.post("/api/devops/parse-yaml",
                          json={"source": "ado", "yaml": yaml_str})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["spec"]["name"] == "ado-pipeline"


class TestF1RouteRegistered:
    """Centinela: ruta registrada en create_app()."""

    def test_f1_route_registered(self):
        """La ruta /api/devops/health está registrada."""
        from app import create_app
        app = create_app()
        rules = [r.rule for r in app.url_map.iter_rules()]
        assert "/api/devops/health" in rules


class TestF1SpecShapeFrozen:
    """Centinela anti-drift del contrato TS↔Python (ADICIÓN ARQUITECTO)."""

    def test_f1_spec_shape_frozen(self):
        """Si este test rompe, actualizar frontend/src/devops/specBuilder.ts (tipos espejo)
        Y estas listas, en el MISMO commit. Protege a los planes 88/89 de la serie."""
        from dataclasses import asdict
        from services.pipeline_spec import dict_to_spec
        spec = asdict(dict_to_spec({
            "name": "p", "stages": [{"name": "s", "jobs": [
                {"name": "j", "steps": [{"name": "st", "script": "echo"}]}
            ]}],
        }))
        assert sorted(spec.keys()) == ["name", "raw_yaml", "raw_yaml_target", "stages", "trigger_branches", "variables"]
        assert sorted(spec["stages"][0].keys()) == ["condition", "jobs", "name"]
        assert sorted(spec["stages"][0]["jobs"][0].keys()) == ["artifacts", "image", "name", "pool_vm_image", "runner_tags", "services", "steps", "variables"]
        assert sorted(spec["stages"][0]["jobs"][0]["steps"][0].keys()) == ["condition", "env", "name", "script", "working_directory"]

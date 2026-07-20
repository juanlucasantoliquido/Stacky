"""Snapshot del arnés vivo → backend/harness_defaults.env (versionado).

Lee el/los .env del deploy vivo, se queda SOLO con las claves del arnés
(FLAG_REGISTRY) y las escribe a un archivo versionado que build_release.ps1
hornea como default de cada deploy generado.

Por qué filtramos por FLAG_REGISTRY:
- Garantiza que NUNCA se exporten credenciales/secretos (ADO_PAT, tokens, etc.):
  esas claves no están en el registry, así que se descartan por construcción.
- El archivo resultante es exactamente "el arnés", nada más.

Precedencia de fuentes (la última gana):
  1. <deploy>/backend/_internal/.env  — donde la UI escribía en deploys viejos
     (antes del fix del split writer/loader).
  2. <deploy>/backend/.env            — lo que config.py carga al arrancar y
     donde la UI escribe tras el fix. Es autoritativo cuando existe.

Sin deploy vivo (o sin flags en él): se conserva el archivo versionado actual
(no se pisa con vacío). Así build_release sigue horneando el último snapshot.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = APP_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.harness_flags import FLAG_REGISTRY  # noqa: E402

HARNESS_KEYS = frozenset(spec.key for spec in FLAG_REGISTRY)


def _bool_to_env(val: object) -> str:
    return "true" if val else "false"


def registry_default_values() -> dict[str, str]:
    """Defaults EFECTIVOS del arnés como {key: valor .env}, FIEL al backend DEV.

    Fuente de verdad = el estado real que aplica el backend DEV de ESTE checkout
    (el que el operador levanta con start_dashboard.bat): backend/.env + defaults
    de código. Al importar `config` se dispara `load_dotenv(backend/.env)`, así que
    tanto los atributos de Config como os.environ ya reflejan lo que el operador
    tiene activado en dev.

    - Flag que es atributo de Config (no env_only): se lee `config.<KEY>`, que ya
      incorpora backend/.env (refleja EXEC_VERIFICATION_MODE=annotate,
      FAKE_GREEN_GUARD_HARD=false, y cualquier override del operador), no el
      type-zero declarado.
    - Flag env_only: si el operador la definió explícitamente en backend/.env
      (presente en os.environ tras el load_dotenv), se hornea ESE valor real — así
      una env_only que el operador prendió/apagó en dev llega FIEL al deploy (antes
      se horneaba siempre su spec.default, causando drift). Si NO está definida:
      bool → default seguro declarado (spec.default o False); no-bool con default
      declarado → ese default; no-bool SIN default → se OMITE (su default real vive
      en el call-site y el type-zero podría violar bounds, p.ej. ADO_EDIT_SWEEP_HOURS
      min=1).

    Solo itera FLAG_REGISTRY, así que NUNCA hornea credenciales/secretos (no están
    en el registry). Semilla de MENOR precedencia (un --deploy-root, si se pasa, la pisa).
    """
    from config import config as _cfg  # noqa: PLC0415 (dispara load_dotenv del backend dev)

    out: dict[str, str] = {}
    for spec in FLAG_REGISTRY:
        if not spec.env_only and hasattr(_cfg, spec.key):
            # Fuente de verdad: el atributo efectivo de Config (refleja backend/.env).
            val = getattr(_cfg, spec.key)
            out[spec.key] = _bool_to_env(val) if spec.type == "bool" else str(val)
            continue

        # env_only (o, raro, atributo ausente): honrar el override EXPLÍCITO del dev.
        raw = os.getenv(spec.key)
        if raw is not None:
            if spec.type == "bool":
                out[spec.key] = _bool_to_env(str(raw).strip().lower() in ("1", "true", "yes", "on"))
            else:
                out[spec.key] = raw
        elif spec.type == "bool":
            # env_only bool sin override: default seguro declarado (spec.default o False).
            out[spec.key] = _bool_to_env(spec.default)
        elif spec.default is not None:
            # env_only no-bool CON default declarado explícito.
            out[spec.key] = str(spec.default)
        # else: env_only no-bool SIN default ni override → OMITIR (call-site aplica
        # su propio default válido; evita hornear un type-zero que viole bounds).
    return out

_HEADER = (
    "# harness_defaults.env — Snapshot del arnés que se hornea como default del deploy.\n"
    "# GENERADO por deployment/export_harness_defaults.py desde el deploy vivo.\n"
    "# Solo contiene flags del arnés (FLAG_REGISTRY); NUNCA credenciales ni secretos.\n"
    "# Para refrescarlo con tu config actual: volvé a generar el deploy\n"
    "# (PrepararPublicacion*.bat) — el build lo regenera y lo hornea solo.\n"
)


def parse_env_file(path: Path) -> dict[str, str]:
    """Parsea un .env a dict clave=valor. Ignora comentarios y líneas vacías."""
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        result[key.strip()] = val.strip()
    return result


def collect_harness_defaults(sources: list[Path]) -> dict[str, str]:
    """Mergea las claves del arnés de cada fuente (la última fuente gana)."""
    merged: dict[str, str] = {}
    for src in sources:
        for key, val in parse_env_file(src).items():
            if key in HARNESS_KEYS:
                merged[key] = val
    return merged


def render(defaults: dict[str, str]) -> str:
    """Texto final del archivo: header + flags ordenadas alfabéticamente."""
    lines = [_HEADER.rstrip("\n"), ""]
    for key in sorted(defaults):
        lines.append(f"{key}={defaults[key]}")
    return "\n".join(lines) + "\n"


def deploy_env_sources(deploy_root: Path) -> list[Path]:
    """Fuentes .env dentro del deploy vivo, en orden de precedencia creciente."""
    backend = deploy_root / "backend"
    return [
        backend / "_internal" / ".env",  # legacy (writer viejo) — menor precedencia
        backend / ".env",                # autoritativo tras el fix — gana
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deploy-root",
        default="",
        help="Root del deploy vivo (DeployStackyAgents). Vacío = no leer deploy.",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Destino versionado (típicamente backend/harness_defaults.env).",
    )
    parser.add_argument(
        "--seed-registry-defaults",
        action="store_true",
        help=(
            "Siembra el snapshot con los defaults DECLARADOS del FLAG_REGISTRY "
            "(código) como fuente de MENOR precedencia. El deploy vivo, si existe, "
            "los pisa. Úsalo cuando no hay deploy vivo pero querés hornear los "
            "defaults del código (p.ej. tras cambiar defaults en harness_flags/config)."
        ),
    )
    args = parser.parse_args()

    out = Path(args.out).resolve()

    # Precedencia creciente (la última gana):
    #   1. defaults EFECTIVOS del código (opt-in, --seed-registry-defaults): la
    #      línea base de "el arnés por default" cuando no hay deploy vivo. Refleja
    #      config.py exactamente (MODE=annotate, HARD=false, etc.), sin arrastrar el
    #      snapshot viejo (que podía contradecir un cambio de default del código).
    #   2. deploy vivo (--deploy-root), autoritativo (si se pasa, pisa la semilla).
    # Sin ninguna fuente, se conserva el snapshot vigente (rama `if not defaults`).
    defaults: dict[str, str] = {}
    if args.seed_registry_defaults:
        defaults.update(registry_default_values())

    sources: list[Path] = []
    if args.deploy_root:
        sources = deploy_env_sources(Path(args.deploy_root).resolve())
    defaults.update(collect_harness_defaults(sources))

    if not defaults:
        if out.is_file():
            print(
                f"[harness_defaults] sin flags en el deploy vivo; conservo {out}"
            )
            return 0
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render({}), encoding="utf-8")
        print(f"[harness_defaults] sin deploy vivo; escribí header vacío en {out}")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(defaults), encoding="utf-8")
    print(f"[harness_defaults] {len(defaults)} flags del arnés escritos en {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

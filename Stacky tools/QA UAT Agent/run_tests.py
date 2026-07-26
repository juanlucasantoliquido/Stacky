"""Plan 214 F0 — Runner de specs de Playwright del QA UAT Agent.

Antes tenía hardcodeada la ruta absoluta de OTRO repositorio, que no existe en
este árbol: cualquiera que lo corriera sacaba conclusiones falsas. Ahora la base
es la carpeta de este archivo y los specs se pasan por CLI.

Precedencia de configuración, de mayor a menor:
    variables ya exportadas  >  archivo AGENDA_WEB_ENV_FILE  >  default local

Un archivo de secretos ausente NO es un error: es el caso normal de un smoke
local contra la instancia de desarrollo.
"""
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

env = os.environ.copy()

secrets = os.environ.get("AGENDA_WEB_ENV_FILE", "").strip()
if secrets and Path(secrets).is_file():
    with open(secrets, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                # setdefault: lo que el operador ya exportó gana sobre el archivo.
                env.setdefault(k.strip(), v.strip())

env.setdefault("AGENDA_WEB_USER", "PACIFICO")
env.setdefault("AGENDA_WEB_PASS", "PACIFICO")
env.setdefault("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")

specs = sys.argv[1:]
if not specs:
    print("uso: python run_tests.py <spec.ts> [<spec.ts> ...]")
    sys.exit(2)

cmd = (
    r'"node_modules\.bin\playwright.cmd" test '
    + " ".join(f'"{s}"' for s in specs)
    + " --reporter=list"
)
print(f"BASE: {BASE}")
print(f"URL:  {env['AGENDA_WEB_BASE_URL']}")
print(f"CMD:  {cmd}")

result = subprocess.run(cmd, cwd=str(BASE), env=env, shell=True)
print(f"EXIT CODE: {result.returncode}")
sys.exit(result.returncode)

import os, subprocess, sys

BASE = r"N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky tools\QA UAT Agent"
SECRETS = r"N:\GIT\RS\RSPACIFICO\Tools\Stacky\.secrets\agenda_web.env"

env = os.environ.copy()
with open(SECRETS, encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()

env['AGENDA_WEB_USER'] = 'PACIFICO'
env['AGENDA_WEB_PASS'] = 'PACIFICO'
env['AGENDA_WEB_BASE_URL'] = 'http://localhost:35017/AgendaWeb/'
print(f"ENV OK: USER={env['AGENDA_WEB_USER']} URL={env['AGENDA_WEB_BASE_URL']}")

specs = [
    r"evidence\116\tests\p01_counter_positive.spec.ts",
    r"evidence\116\tests\p02_counter_boundary.spec.ts",
    r"evidence\116\tests\p10_counter_refresh_pos.spec.ts",
]

cmd = r'"node_modules\.bin\playwright.cmd" test ' + ' '.join(f'"{s}"' for s in specs) + ' --reporter=list'
print(f"CMD: {cmd}")
result = subprocess.run(cmd, cwd=BASE, env=env, shell=True)
print(f"EXIT CODE: {result.returncode}")
sys.exit(result.returncode)
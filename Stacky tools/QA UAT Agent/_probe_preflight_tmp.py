"""Sonda: preflight de entorno + login real de AgendaWeb (solo lectura)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from environment_preflight import run_environment_preflight, get_agenda_base_url  # noqa: E402

print("BASE_URL:", get_agenda_base_url())
res = run_environment_preflight()
d = res.to_pipeline_dict() if hasattr(res, "to_pipeline_dict") else vars(res)
print(json.dumps(d, indent=2, default=str)[:3000])

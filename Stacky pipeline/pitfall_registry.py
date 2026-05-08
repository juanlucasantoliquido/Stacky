"""
pitfall_registry.py — G-02: Cross-ticket Pitfall Memory.

Registra errores recurrentes detectados por QA/validador y los inyecta
como advertencias en el próximo prompt DEV del mismo tipo de archivo.

Uso:
    from pitfall_registry import PitfallRegistry
    registry = PitfallRegistry()
    registry.register("dalc", "Rows[0] sin guard Count > 0", "INC-123")
    warnings = registry.get_warnings_for_files(["Batch/Negocio/PagosDalc.cs"])
"""

import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("stacky.pitfall_registry")

REGISTRY_FILE = Path(__file__).parent / "data" / "pitfall_registry.json"

class PitfallRegistry:
    def __init__(self, registry_file: Path = REGISTRY_FILE):
        self._file = registry_file

    def register(self, file_pattern: str, description: str, source_ticket: str) -> None:
        """Register a pitfall detected by QA for a file type/pattern."""
        registry = self._load()
        key = file_pattern.lower()
        if key not in registry:
            registry[key] = []
        
        # Check if this exact pitfall already exists — increment occurrences
        for existing in registry[key]:
            if existing["description"].lower() == description.lower():
                existing["occurrences"] += 1
                existing["last_seen"] = datetime.now().isoformat()
                existing["tickets"].append(source_ticket)
                self._save(registry)
                logger.info("[Pitfall] Incrementado: '%s' en '%s' (%dx)", 
                           description, key, existing["occurrences"])
                return
        
        # New pitfall
        registry[key].append({
            "description": description,
            "tickets": [source_ticket],
            "first_seen": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "occurrences": 1,
        })
        self._save(registry)
        logger.info("[Pitfall] Registrado nuevo: '%s' en '%s'", description, key)

    def get_warnings_for_files(self, file_list: list[str]) -> list[str]:
        """
        Given a list of files that DEV is going to modify,
        return warnings for known pitfalls in those file types.
        """
        registry = self._load()
        warnings = []
        for f in file_list:
            f_lower = f.lower()
            for pattern, pitfalls in registry.items():
                if pattern in f_lower or self._match_file_type(f_lower, pattern):
                    for p in sorted(pitfalls, key=lambda x: -x["occurrences"])[:3]:
                        tickets_str = ", ".join(p["tickets"][-3:])
                        warnings.append(
                            f"PITFALL CONOCIDO en archivos tipo '{pattern}': {p['description']} "
                            f"(detectado {p['occurrences']}x, tickets: {tickets_str})"
                        )
        return warnings

    def get_all_pitfalls(self) -> dict:
        """Return the full registry for inspection."""
        return self._load()

    def _match_file_type(self, filename: str, pattern: str) -> bool:
        """Check if a filename matches a pattern like 'dalc', 'aspx', 'sql'."""
        type_patterns = {
            "dalc": ["dalc.cs", "dalc.vb"],
            "aspx": [".aspx", ".aspx.cs"],
            "sql": [".sql"],
            "negocio": ["negocio/", "negocio\\"],
            "batch": ["batch/", "batch\\"],
            "online": ["online/", "online\\"],
        }
        matchers = type_patterns.get(pattern, [pattern])
        return any(m in filename for m in matchers)

    def _load(self) -> dict:
        if self._file.exists():
            try:
                return json.loads(self._file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("[Pitfall] Error leyendo registry: %s", e)
        return {}

    def _save(self, registry: dict) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

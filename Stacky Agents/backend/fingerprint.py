"""
N3 — Ticket Pre-Analysis Fingerprint (TPAF) — Fase 1: keyword-based

Analiza el título y descripción de un ticket y retorna metadata pre-calculada:
- Tipo de cambio (feature / bug / refactor / config)
- Dominio funcional detectado (cobros, créditos, etc.)
- Complejidad estimada (S / M / L / XL)
- Pack sugerido
- Keywords detectadas

Fase 1 usa heurísticas puras (sin LLM). Fase 3+ migra a TPAF semántico con embeddings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models import Ticket

# ---------------------------------------------------------------------------
# Mapas de keywords
# ---------------------------------------------------------------------------

_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "cobros": ["cobro", "cobranza", "deuda", "pago", "cuota", "mora", "vencimiento", "importe"],
    "créditos": ["crédito", "credito", "préstamo", "prestamo", "tasa", "capital", "cuotas", "amortización"],
    "notificaciones": ["sms", "email", "notif", "mensaje", "alerta", "aviso", "correo", "push"],
    "usuarios": ["usuario", "operador", "acceso", "login", "perfil", "sesión", "rol", "permiso"],
    "batch": ["batch", "proceso", "carga", "archivo", "bkp", "backup", "masivo", "scheduler"],
    "online": ["online", "servicio", "api", "rest", "endpoint", "web", "http", "microservicio"],
    "base_de_datos": ["bd", "tabla", "sql", "sp ", "procedimiento", "índice", "view", "query", "ridioma"],
    "seguridad": ["seguridad", "cifrado", "encriptación", "autenticación", "autorización", "token"],
}

_CHANGE_TYPE_RULES: list[tuple[list[str], str]] = [
    (["bug", "error", "falla", "fallo", "fix", "corregir", "incidente", "hotfix", "defecto"], "bug"),
    (["refactor", "optimizar", "mejorar performance", "cleanup", "reestructurar", "simplificar"], "refactor"),
    (["config", "configurar", "parámetro", "parametro", "ajuste", "setting"], "config"),
    (["nuevo", "nueva", "agregar", "crear", "implementar", "integrar", "desarrollar", "feature"], "feature"),
]

_COMPLEXITY_WEIGHTS: list[tuple[str, int]] = [
    ("integración", 3),
    ("migración", 3),
    ("microservicio", 3),
    ("módulo completo", 3),
    ("nuevo flujo", 2),
    ("nuevo", 2),
    ("nueva", 2),
    ("api", 2),
    ("batch", 2),
    ("base de datos", 2),
    ("refactor", 2),
    ("módulo", 2),
    ("flujo", 2),
    ("performance", 2),
    ("bug", 1),
    ("fix", 1),
    ("config", 1),
    ("ajuste", 1),
    ("parámetro", 1),
]

_PACK_TRIGGERS: list[tuple[list[str], str]] = [
    (["bug", "fix", "hotfix", "corregir", "incidente", "defecto", "validar", "verificar", "qa"], "qa-express"),
    (["nuevo", "nueva", "feature", "implementar", "integrar", "desarrollar", "crear módulo"], "desarrollo"),
]


# ---------------------------------------------------------------------------
# Dataclass resultado
# ---------------------------------------------------------------------------

@dataclass
class TicketFingerprint:
    ticket_ado_id: int
    change_type: str           # "feature" | "bug" | "refactor" | "config" | "unknown"
    domain: list[str]          # dominios detectados
    complexity: str            # "S" | "M" | "L" | "XL"
    suggested_pack: str        # id del pack sugerido
    domain_confidence: float   # 0.0 – 1.0
    keywords_detected: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ticket_ado_id": self.ticket_ado_id,
            "change_type": self.change_type,
            "domain": self.domain,
            "complexity": self.complexity,
            "suggested_pack": self.suggested_pack,
            "domain_confidence": round(self.domain_confidence, 2),
            "keywords_detected": self.keywords_detected,
        }


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def analyze(ticket: "Ticket") -> TicketFingerprint:
    """Analiza un ticket y devuelve su fingerprint. Fase 1: keyword-based, sin LLM."""
    text = f"{ticket.title or ''} {ticket.description or ''}".lower()

    # 1. Detectar dominios
    domains: list[str] = []
    detected_kws: list[str] = []
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        hits = [kw for kw in keywords if kw in text]
        if hits:
            domains.append(domain)
            detected_kws.extend(hits)

    # Confianza basada en cuántos keywords distintos se encontraron
    domain_confidence = min(len(set(detected_kws)) / 4.0, 1.0)

    # 2. Tipo de cambio (primera regla que matchea gana)
    change_type = "unknown"
    for triggers, ctype in _CHANGE_TYPE_RULES:
        if any(t in text for t in triggers):
            change_type = ctype
            break

    # 3. Complejidad
    complexity_score = 0
    for phrase, weight in _COMPLEXITY_WEIGHTS:
        if phrase in text:
            complexity_score += weight

    if complexity_score <= 2:
        complexity = "S"
    elif complexity_score <= 5:
        complexity = "M"
    elif complexity_score <= 9:
        complexity = "L"
    else:
        complexity = "XL"

    # 4. Pack sugerido
    suggested_pack = "desarrollo"  # default
    for triggers, pack_id in _PACK_TRIGGERS:
        if any(t in text for t in triggers):
            suggested_pack = pack_id
            break

    return TicketFingerprint(
        ticket_ado_id=ticket.ado_id,
        change_type=change_type,
        domain=domains if domains else ["general"],
        complexity=complexity,
        suggested_pack=suggested_pack,
        domain_confidence=domain_confidence,
        keywords_detected=list(set(detected_kws))[:10],  # máx 10 keywords
    )

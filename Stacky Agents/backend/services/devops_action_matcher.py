"""Plan 267 F2 — Matcher de intencion DETERMINISTA. Sin modelo, sin red, sin IO.

Es el piso de paridad: con GitHub Copilot (o sin runtime disponible) este matcher
es TODO el motor de intencion, y alcanza para proponer y previsualizar.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from services.devops_action_catalog import DevOpsAction

MIN_SCORE = 0.6          # por debajo => no hay match
AMBIGUITY_DELTA = 0.10   # si top1 - top2 < esto => needs_disambiguation
MAX_MATCHES = 3

_NON_WORD = re.compile(r"[^a-z0-9 ]+")   # v2: la n~ se fue en el paso NFD+Mn de
                                         # normalize_text (n + tilde combinante);
                                         # dejarla en la clase era regla muerta [C17]
_SPACES = re.compile(r"\s+")

# v2 [C2] — FIX BLOQUEANTE. Sin esto, "quiero disparar la piplain" puntuaba
# 2/3 = 0.667 >= MIN_SCORE contra la frase "disparar la pipeline", porque el
# articulo "la" contaba como token de contenido. El test 4 salia ROJO el dia 1.
# Las stopwords NO se borran del texto: se excluyen del DENOMINADOR y del
# numerador, para que el score mida solo palabras que significan algo.
_STOPWORDS = frozenset((
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "al", "a", "en", "con", "por", "para", "sobre",
    "y", "o", "que", "se", "lo", "mi", "me", "te", "su",
    "quiero", "necesito", "podes", "puedo", "hace", "haceme", "dame",
    "mostrame", "decime", "porfa", "please",
))


def _content_tokens(text: str) -> list[str]:
    """Tokens que significan algo: no vacios y no stopwords. NUNCA lanza."""
    return [t for t in (text or "").split(" ") if t and t not in _STOPWORDS]


@dataclass(frozen=True)
class ActionMatch:
    action_id: str
    score: float          # 0.0 .. 1.0
    matched_phrase: str


def normalize_text(text: str | None) -> str:
    """minusculas + sin acentos + sin puntuacion + espacios colapsados. NUNCA lanza."""
    if not text:
        return ""
    s = unicodedata.normalize("NFD", str(text).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = _NON_WORD.sub(" ", s)
    return _SPACES.sub(" ", s).strip()


def _phrase_score(norm_text: str, phrase: str) -> float:
    """Cobertura de tokens DE CONTENIDO de la frase presentes en el texto, mas un
    bonus por aparicion literal. Determinista y acotado a [0,1]. NUNCA lanza.

    v2 [C2]: los articulos y muletillas no cuentan ni arriba ni abajo. Con la
    frase "disparar la pipeline" los tokens de contenido son ("disparar",
    "pipeline"); "quiero disparar la piplain" da 1/2 = 0.5 < MIN_SCORE => NO
    matchea, que es lo que el test 4 siempre quiso afirmar.
    """
    norm_phrase = normalize_text(phrase)
    tokens = _content_tokens(norm_phrase)
    if not tokens:
        return 0.0
    text_tokens = set(_content_tokens(norm_text))
    hits = sum(1 for t in tokens if t in text_tokens)
    base = hits / len(tokens)
    if norm_phrase and norm_phrase in norm_text:
        base = min(1.0, base + 0.15)
    return round(base, 4)


def match_intent(text: str | None, actions: list[DevOpsAction]) -> list[ActionMatch]:
    """Devuelve hasta MAX_MATCHES matches con score >= MIN_SCORE, ordenados por
    score DESC y, ante empate exacto, por el ORDEN DEL CATALOGO (estable).
    Lista vacia = no entendi. NUNCA lanza."""
    norm = normalize_text(text)
    if not norm:
        return []
    scored: list[tuple[float, int, ActionMatch]] = []
    for idx, a in enumerate(actions or []):
        best, best_phrase = 0.0, ""
        for candidate in (*a.phrases, a.label):
            s = _phrase_score(norm, candidate)
            if s > best:
                best, best_phrase = s, candidate
        if best >= MIN_SCORE:
            scored.append((best, idx, ActionMatch(a.id, best, best_phrase)))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [m for _, _, m in scored[:MAX_MATCHES]]


def is_ambiguous(matches: list[ActionMatch]) -> bool:
    """True si hay >= 2 matches y la diferencia de score es menor a AMBIGUITY_DELTA."""
    if len(matches) < 2:
        return False
    return (matches[0].score - matches[1].score) < AMBIGUITY_DELTA

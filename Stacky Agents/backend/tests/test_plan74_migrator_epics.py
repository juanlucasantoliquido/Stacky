"""Plan 74 F3 — Tests de migrator_epics.py (resolve_epic_strategy).

6 casos.
"""
from unittest.mock import MagicMock
import pytest

from services.migrator_epics import resolve_epic_strategy, EpicDecision


def _provider(epics_native: bool = True):
    p = MagicMock()
    p._epics_native = epics_native
    return p


def _provider_no_attr():
    """Provider sin atributo _epics_native (mock genérico)."""
    p = MagicMock(spec=[])  # spec vacío: no tiene ningún atributo predefinido
    return p


def test_auto_con_epics_native_true():
    """policy='auto' + provider._epics_native=True → premium_native."""
    p = _provider(epics_native=True)
    dec = resolve_epic_strategy(p, "auto")
    assert dec.strategy == "premium_native"
    assert dec.item_type_for_create == "epic"


def test_auto_con_epics_native_false():
    """policy='auto' + provider._epics_native=False → free_degrade."""
    p = _provider(epics_native=False)
    dec = resolve_epic_strategy(p, "auto")
    assert dec.strategy == "free_degrade"
    assert dec.item_type_for_create == "issue"
    assert "type::epic" in dec.extra_labels


def test_free_degrade_siempre():
    """policy='free_degrade' → siempre free_degrade sin importar el provider."""
    p = _provider(epics_native=True)
    dec = resolve_epic_strategy(p, "free_degrade")
    assert dec.strategy == "free_degrade"


def test_premium_native_siempre():
    """policy='premium_native' → siempre premium_native."""
    p = _provider(epics_native=False)
    dec = resolve_epic_strategy(p, "premium_native")
    assert dec.strategy == "premium_native"


def test_auto_sin_atributo_epics_native_default_free_degrade():
    """Provider sin atributo _epics_native + 'auto' → free_degrade (default seguro)."""
    p = _provider_no_attr()
    dec = resolve_epic_strategy(p, "auto")
    assert dec.strategy == "free_degrade"


def test_resolve_no_invoca_metodos_del_provider():
    """resolve_epic_strategy no invoca ningún método del provider (solo lee atributo)."""
    p = _provider(epics_native=True)
    resolve_epic_strategy(p, "auto")
    # Ningún método del mock debe haber sido llamado
    p.fetch_open_items.assert_not_called()
    p.get_item.assert_not_called()
    p.create_item.assert_not_called()

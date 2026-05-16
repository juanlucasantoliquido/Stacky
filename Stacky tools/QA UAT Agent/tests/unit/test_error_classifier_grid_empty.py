from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def test_error_classifier_grid_empty_is_data_terminal():
    from navigation_driver import classify_error

    result = classify_error("GRID_EMPTY: no rows found after search", "http://localhost/AgendaWeb/FrmBusqueda.aspx")

    assert result["error_code"] == "NAV_DATA_GRID_EMPTY"
    assert result["category"] == "DATA"
    assert result["reason"] == "SEARCH_RESULTS_EMPTY"
    assert result["is_terminal"] is True

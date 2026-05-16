from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def test_error_classifier_apppool_crash_from_status_and_title():
    from navigation_driver import classify_error

    by_status = classify_error(
        "navigation failed",
        "http://localhost/AgendaWeb/FrmDetalleClie.aspx",
        response_status=500,
    )
    by_title = classify_error(
        "page loaded",
        "http://localhost/AgendaWeb/FrmDetalleClie.aspx",
        page_title="Runtime Error",
    )

    for result in (by_status, by_title):
        assert result["error_code"] == "NAV_SERVER_ERROR"
        assert result["category"] == "ENV"
        assert result["reason"] == "ASPNET_APPPOOL_ERROR"
        assert result["is_terminal"] is True


def test_error_classifier_errors_aspx_redirect():
    from navigation_driver import classify_error

    result = classify_error("redirected", "http://localhost/AgendaWeb/Errors.aspx")

    assert result["error_code"] == "NAV_SERVER_ERROR"
    assert result["category"] == "ENV"
    assert result["reason"] == "ASPNET_REDIRECT_TO_ERRORS_PAGE"
    assert result["is_terminal"] is True

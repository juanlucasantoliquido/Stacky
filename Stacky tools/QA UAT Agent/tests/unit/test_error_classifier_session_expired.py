from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def test_error_classifier_session_expired_is_terminal_env():
    from navigation_driver import classify_error

    result = classify_error(
        "Timeout waiting for FrmDetalleClie",
        "http://localhost/AgendaWeb/FrmLogin.aspx",
    )

    assert result == {
        "error_code": "NAV_AUTH_EXPIRED",
        "category": "ENV",
        "reason": "SESSION_EXPIRED_LOGIN_REDIRECT",
        "is_terminal": True,
    }

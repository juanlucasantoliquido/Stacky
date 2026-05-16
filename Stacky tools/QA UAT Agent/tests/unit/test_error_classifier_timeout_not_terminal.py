from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def test_error_classifier_timeout_is_retriable_nav():
    from navigation_driver import classify_error

    result = classify_error("Timeout 45000ms exceeded while waiting for URL", "")

    assert result["error_code"] == "NAV_TIMEOUT"
    assert result["category"] == "NAV"
    assert result["reason"] == "NAVIGATION_TIMEOUT"
    assert result["is_terminal"] is False

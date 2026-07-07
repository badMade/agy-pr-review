import sys
from unittest.mock import MagicMock

# Mock out the google.antigravity module before importing run_agent
sys.modules['google'] = MagicMock()
sys.modules['google.antigravity'] = MagicMock()
sys.modules['google.antigravity.hooks'] = MagicMock()

from run_agent import _build_policy_addendum

def test_build_policy_addendum_empty():
    assert _build_policy_addendum("") == ""
    assert _build_policy_addendum("SOME_OTHER_FLAG=true") == ""

def test_build_policy_addendum_ts_type_safety():
    result = _build_policy_addendum("ENFORCE_TS_TYPE_SAFETY=true")
    assert "Active Policy Override: TypeScript Type Safety (ENFORCED)" in result
    assert "Active Policy Override: Unit Test Coverage" not in result

def test_build_policy_addendum_perf_regression():
    result = _build_policy_addendum("FLAG_PERF_REGRESSIONS=true")
    assert "Active Policy Override: Performance Regression (ENFORCED)" in result

def test_build_policy_addendum_security_compliance():
    result = _build_policy_addendum("ENFORCE_SECURITY_COMPLIANCE=true")
    assert "Active Policy Override: Security Compliance (ENFORCED)" in result

def test_build_policy_addendum_unit_test_coverage():
    result = _build_policy_addendum("ENFORCE_TEST_COVERAGE=true")
    assert "Active Policy Override: Unit Test Coverage (ENFORCED)" in result
    assert "Active Policy Override: TypeScript Type Safety" not in result

def test_build_policy_addendum_multiple():
    result = _build_policy_addendum("ENFORCE_TS_TYPE_SAFETY=true FLAG_PERF_REGRESSIONS=true ENFORCE_SECURITY_COMPLIANCE=true ENFORCE_TEST_COVERAGE=true")
    assert "Active Policy Override: TypeScript Type Safety (ENFORCED)" in result
    assert "Active Policy Override: Performance Regression (ENFORCED)" in result
    assert "Active Policy Override: Security Compliance (ENFORCED)" in result
    assert "Active Policy Override: Unit Test Coverage (ENFORCED)" in result
    # It should be joined by \n, so there is at least a \n between the strings
    assert "\n" in result

from devin_proxy.models.catalog import SWE2_TIERS, resolve_model


def test_only_swe2_lanes():
    for m in ("swe-2", "swe2", "swe", "", None):
        assert resolve_model(m) in SWE2_TIERS


def test_effort_max():
    assert resolve_model("swe-2", "max") == "swe-2-max"
    assert resolve_model("swe-2", "xhigh") == "swe-2-max"


def test_effort_medium():
    for e in ("medium", "low", "minimal", "none", "off"):
        assert resolve_model("swe-2", e) == "swe-2-medium"


def test_explicit_tier_wins():
    assert resolve_model("swe-2-max") == "swe-2-max"
    assert resolve_model("swe-2-medium") == "swe-2-medium"


def test_unknown_model_defaults():
    assert resolve_model("gpt-4o") in SWE2_TIERS
    assert resolve_model("claude-3") in SWE2_TIERS

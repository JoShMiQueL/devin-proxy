from devin_proxy.models.catalog import (
    ALL_TIERS,
    SWE2_FLASH_TIERS,
    SWE2_TIERS,
    resolve_model,
)


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


def test_flash_family():
    assert resolve_model("swe-2-flash") == "swe-2-flash-high"
    assert resolve_model("flash") == "swe-2-flash-high"
    assert resolve_model("swe-2-flash", "max") == "swe-2-flash-max"
    assert resolve_model("swe-2-flash", "low") == "swe-2-flash-medium"
    for e in ("medium", "low", "minimal", "none", "off"):
        assert resolve_model("swe-2-flash", e) == "swe-2-flash-medium"


def test_flash_explicit_tier():
    assert resolve_model("swe-2-flash-medium") == "swe-2-flash-medium"
    assert resolve_model("swe-2-flash-max") == "swe-2-flash-max"
    assert resolve_model("swe2-flash-high") == "swe-2-flash-high"


def test_lightning_not_routed():
    # lightning lanes bill fast-mode credits — never resolve to them
    assert resolve_model("swe-2-lightning") in SWE2_TIERS
    assert resolve_model("swe-2-medium-lightning") in SWE2_TIERS
    assert "lightning" not in resolve_model("swe-2-lightning", "max")


def test_allowed_models_restricts():
    allowed = ("swe-2-high", "swe-2-flash-high")
    assert resolve_model("swe-2-max", allowed=allowed) == "swe-2-high"
    assert resolve_model("swe-2-flash-high", allowed=allowed) \
        == "swe-2-flash-high"
    allowed2 = ("swe-2-high",)
    assert resolve_model("swe-2-flash", allowed=allowed2) == "swe-2-high"


def test_all_tiers_contains_everything():
    assert set(SWE2_TIERS) | set(SWE2_FLASH_TIERS) <= set(ALL_TIERS)


def test_allow_paid_setting():
    import os

    from devin_proxy.config import Settings, load_settings
    assert not Settings().allow_paid
    os.environ["DEVIN_PROXY_ALLOW_PAID"] = "1"
    try:
        assert load_settings().allow_paid
    finally:
        del os.environ["DEVIN_PROXY_ALLOW_PAID"]


def test_paid_uid_passthrough_logic():
    # Engine._catalog_uids + the allow_paid gate in run(): a paid uid in the
    # catalog routes verbatim only when allow_paid is set.
    from types import SimpleNamespace

    from devin_proxy.pipeline import Engine

    cat = [SimpleNamespace(uid="claude-opus-5-max"),
           SimpleNamespace(uid="swe-2-high")]
    eng = Engine.__new__(Engine)
    eng.catalog = cat
    assert eng._catalog_uids() == {"claude-opus-5-max", "swe-2-high"}
    eng.catalog = None
    assert eng._catalog_uids() == set()

"""Outfit preference shifts the decision temperature and the visible layers."""

from app.services.outfit_preference import apply_outfit_preference


def _comfort_outfit() -> dict:
    """A mild outfit: T-shirt, no mid layer, no outer layer."""
    return {
        "effective_temperature_celsius": 19.0,
        "base_layer": {"id": "light_t_shirt", "label": "Light T-shirt", "category": "BASE"},
        "mid_layer": None,
        "outer_layer": None,
        "accessories": [{"id": "sunglasses", "label": "Sunglasses", "category": "ACCESSORY"}],
    }


def _layered_outfit() -> dict:
    """A cool outfit with a fleece and a light jacket."""
    return {
        "effective_temperature_celsius": 11.6,
        "base_layer": {"id": "long_sleeve_base", "label": "Long-sleeve base layer", "category": "BASE"},
        "mid_layer": {"id": "fleece_mid_layer", "label": "Fleece mid-layer", "category": "MID"},
        "outer_layer": {"id": "light_jacket", "label": "Light jacket", "category": "OUTER"},
        "accessories": [{"id": "sunglasses", "label": "Sunglasses", "category": "ACCESSORY"}],
    }


def test_warm_lowers_temperature_and_adds_outer_hat_and_gloves() -> None:
    """Warm mode steps a bare outfit up to a jacket, hat, and gloves."""
    outfit = _comfort_outfit()

    assert apply_outfit_preference(outfit, "warm", rain_probability_percent=0.0) == "warm"
    assert outfit["effective_temperature_celsius"] == 17.0
    assert outfit["outer_layer"]["id"] == "light_jacket"
    accessory_ids = {item["id"] for item in outfit["accessories"]}
    assert {"warm_hat", "gloves", "sunglasses"} <= accessory_ids


def test_warm_upgrades_a_light_jacket_to_a_winter_coat() -> None:
    """A jacket already in the outfit becomes a winter coat, with hat and gloves."""
    outfit = _layered_outfit()

    apply_outfit_preference(outfit, "warm", rain_probability_percent=0.0)

    assert outfit["effective_temperature_celsius"] == 9.6
    assert outfit["outer_layer"]["id"] == "winter_coat"
    assert outfit["mid_layer"]["id"] == "fleece_mid_layer"
    accessory_ids = {item["id"] for item in outfit["accessories"]}
    assert {"warm_hat", "gloves"} <= accessory_ids


def test_light_raises_temperature_and_drops_mid_and_outer() -> None:
    """Light mode removes the mid layer and a dry-weather jacket."""
    outfit = _layered_outfit()

    assert apply_outfit_preference(outfit, "light", rain_probability_percent=0.0) == "light"
    assert outfit["effective_temperature_celsius"] == 13.6
    assert outfit["mid_layer"] is None
    assert outfit["outer_layer"] is None
    assert [item["id"] for item in outfit["accessories"]] == ["sunglasses"]


def test_light_keeps_a_waterproof_shell_in_the_rain() -> None:
    """Rain still needs a shell after the outfit is lightened."""
    outfit = _layered_outfit()

    apply_outfit_preference(outfit, "light", rain_probability_percent=60.0)

    assert outfit["outer_layer"]["id"] == "waterproof_shell"
    assert outfit["mid_layer"] is None


def test_balanced_and_auto_leave_the_engine_outfit_unchanged() -> None:
    """Balanced wear, including the old auto mode, does not move the outfit."""
    outfit = _layered_outfit()

    assert apply_outfit_preference(outfit, "auto", rain_probability_percent=0.0) == "balanced"
    assert outfit["effective_temperature_celsius"] == 11.6
    assert outfit["mid_layer"]["id"] == "fleece_mid_layer"
    assert outfit["outer_layer"]["id"] == "light_jacket"

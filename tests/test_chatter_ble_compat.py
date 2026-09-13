from serialterminal.profiles.chatter.ble_compat import (
    PINGER_NAME,
    REPEATER_NAME,
    is_chatter_ble_name,
    normalize_chatter_ble_target,
)


def test_chatter_ble_name_hint_is_project_specific():
    assert is_chatter_ble_name("LoRa-Chatter-72E0")
    assert is_chatter_ble_name(PINGER_NAME)
    assert not is_chatter_ble_name("Nordic UART")
    assert not is_chatter_ble_name(None)


def test_chatter_ble_target_legacy_aliases():
    assert normalize_chatter_ble_target("p") == PINGER_NAME
    assert normalize_chatter_ble_target("PINGER") == PINGER_NAME
    assert normalize_chatter_ble_target("r") == REPEATER_NAME
    assert normalize_chatter_ble_target("repeater") == REPEATER_NAME
    assert (
        normalize_chatter_ble_target("LoRa-Chatter-72E0")
        == "LoRa-Chatter-72E0"
    )
    assert normalize_chatter_ble_target("other") is None

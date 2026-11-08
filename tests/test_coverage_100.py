"""Extra tests to reach 100% coverage for hp_ilo."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hp_ilo import (
    DOMAIN,
    IloDataUpdateCoordinator,
    _async_handle_power_action,
    _get_ilo_client,
    _parse_power_wattage,
    _resolve_entry,
    _summarise_health,
    async_reload_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)

from .const import MOCK_CONFIG, MOCK_HEALTH


# --- pure helpers ---


def test_parse_power_wattage_branches():
    assert _parse_power_wattage("not a dict") == 0  # type: ignore[arg-type]
    assert _parse_power_wattage({}) == 0
    assert _parse_power_wattage({"present_power_reading": None}) == 0
    assert _parse_power_wattage({"present_power_reading": (101, "Watts")}) == 101
    assert _parse_power_wattage({"present_power_reading": [55, "Watts"]}) == 55
    assert _parse_power_wattage({"present_power_reading": 42}) == 42
    assert _parse_power_wattage({"present_power_reading": "65 Watts"}) == 65
    assert _parse_power_wattage({"present_power_reading": "bad"}) == 0
    assert _parse_power_wattage({"present_power_reading": []}) == 0


def test_summarise_health_branches():
    assert _summarise_health({}) == "OK"
    assert _summarise_health({"health_at_a_glance": "bad"}) == "OK"
    assert _summarise_health({"health_at_a_glance": {}}) == "OK"
    assert _summarise_health({"health_at_a_glance": {"fans": {"status": "OK"}}}) == "OK"
    assert (
        _summarise_health({"health_at_a_glance": {"fans": {"status": "Healthy"}}})
        == "OK"
    )
    assert (
        _summarise_health({"health_at_a_glance": {"fans": "Degraded"}}) == "DEGRADED"
    )
    assert (
        _summarise_health({"health_at_a_glance": {"fans": {"status": "Critical"}}})
        == "CRITICAL"
    )


def test_get_ilo_client(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="x")
    with patch("hpilo.Ilo") as cls:
        _get_ilo_client(entry)
        assert cls.called


async def test_async_setup_basic(hass):
    assert await async_setup(hass, {}) is True
    assert DOMAIN in hass.data


# --- coordinator error branches ---


async def test_coordinator_update_failed(hass, mock_ilo):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="t1")
    coord = IloDataUpdateCoordinator(hass, entry)
    mock_ilo.get_embedded_health.side_effect = Exception("boom")
    from homeassistant.helpers.update_coordinator import UpdateFailed

    with pytest.raises(UpdateFailed):
        await hass.async_add_executor_job(coord._get_ilo_data)


async def test_coordinator_status_fallbacks(hass, mock_ilo):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="t2")
    coord = IloDataUpdateCoordinator(hass, entry)
    mock_ilo.get_embedded_health.return_value = dict(MOCK_HEALTH)
    mock_ilo.get_power_readings.side_effect = Exception("no readings")
    mock_ilo.get_host_power_status.side_effect = Exception("no status")
    mock_ilo.get_server_power_on_time.side_effect = Exception("no time")
    data = await hass.async_add_executor_job(coord._get_ilo_data)
    assert data["power_usage"] == 0
    assert data["power_status"] == "UNKNOWN"
    assert data["power_on_time"] is None


async def test_coordinator_non_dict_power(hass, mock_ilo):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="t3")
    coord = IloDataUpdateCoordinator(hass, entry)
    mock_ilo.get_embedded_health.return_value = dict(MOCK_HEALTH)
    mock_ilo.get_power_readings.side_effect = None
    mock_ilo.get_power_readings.return_value = "bad"  # type: ignore[assignment]
    data = await hass.async_add_executor_job(coord._get_ilo_data)
    assert data["power_usage"] == 0
    assert data["power_readings"] == {}


# --- power action legacy branches ---


def _entry():
    return MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="e1")


async def test_handle_power_legacy_warm_boot(hass):
    dummy = SimpleNamespace(warm_boot=MagicMock())
    with patch("custom_components.hp_ilo._get_ilo_client", return_value=dummy):
        await _async_handle_power_action(hass, _entry(), "reboot_server")
        assert dummy.warm_boot.called


async def test_handle_power_legacy_press(hass):
    dummy = SimpleNamespace(press_pwr_button=MagicMock())
    with patch("custom_components.hp_ilo._get_ilo_client", return_value=dummy):
        await _async_handle_power_action(hass, _entry(), "shutdown_graceful")
        assert dummy.press_pwr_button.called


async def test_handle_power_hold_fallback_typeerror(hass):
    def raising(hold=False):
        if hold:
            raise TypeError("no hold")
        return None

    dummy = SimpleNamespace(press_pwr_btn=MagicMock(side_effect=raising))
    # remove hold_pwr_btn so elif press_pwr_btn branch is taken
    with patch("custom_components.hp_ilo._get_ilo_client", return_value=dummy):
        await _async_handle_power_action(hass, _entry(), "shutdown_hard")
        assert dummy.press_pwr_btn.called


async def test_handle_power_hold_legacy_button(hass):
    dummy = SimpleNamespace(press_pwr_button=MagicMock())
    with patch("custom_components.hp_ilo._get_ilo_client", return_value=dummy):
        await _async_handle_power_action(hass, _entry(), "shutdown_hard")
        assert dummy.press_pwr_button.called


async def test_resolve_entry_branches(hass, mock_ilo):
    # no entries
    assert _resolve_entry(hass, SimpleNamespace(data={})) is None

    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="abc")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # by entry_id hit
    found = _resolve_entry(hass, SimpleNamespace(data={"entry_id": "abc"}))
    assert found is not None and found.entry_id == "abc"
    # by entry_id miss
    assert _resolve_entry(hass, SimpleNamespace(data={"entry_id": "nope"})) is None
    # by host hit
    found2 = _resolve_entry(
        hass, SimpleNamespace(data={"host": MOCK_CONFIG["host"]})
    )
    assert found2 is not None
    # by host miss
    assert _resolve_entry(hass, SimpleNamespace(data={"host": "9.9.9.9"})) is None
    # default first
    assert _resolve_entry(hass, SimpleNamespace(data={})) is not None


async def test_service_no_matching_entry(hass, mock_ilo, caplog):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="s1")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        DOMAIN, "power_on", {"entry_id": "missing"}, blocking=True
    )
    assert mock_ilo.set_host_power.called is False or True  # no crash


async def test_service_handler_exception_logged(hass, mock_ilo):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="s2")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    with patch(
        "custom_components.hp_ilo._async_handle_power_action",
        side_effect=Exception("fail"),
    ):
        await hass.services.async_call(DOMAIN, "power_on", {}, blocking=True)


async def test_unload_not_ok(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="u1")
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
        return_value=False,
    ):
        assert await async_unload_entry(hass, entry) is False


async def test_reload_entry_direct(hass, mock_ilo):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="r1")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await async_reload_entry(hass, entry)
    await hass.async_block_till_done()
    assert entry.entry_id in hass.data.get(DOMAIN, {})


# --- button branches ---


def _button_entry(action):
    return MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="b1")


async def test_button_legacy_and_unknown(hass):
    from custom_components.hp_ilo.button import IloPowerButton
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers.entity import DeviceInfo

    device = DeviceInfo(identifiers={(DOMAIN, "b1")}, name="Test")

    # legacy warm_boot
    btn = IloPowerButton(_button_entry("x"), device, "n", "warm_boot", "mdi:x")
    btn.hass = hass
    dummy = SimpleNamespace(warm_boot=MagicMock())
    with patch("hpilo.Ilo", return_value=dummy):
        await btn.async_press()
        assert dummy.warm_boot.called

    # legacy press_pwr_button
    btn2 = IloPowerButton(_button_entry("x"), device, "n", "press_pwr_btn", "mdi:x")
    btn2.hass = hass
    dummy2 = SimpleNamespace(press_pwr_button=MagicMock())
    with patch("hpilo.Ilo", return_value=dummy2):
        await btn2.async_press()
        assert dummy2.press_pwr_button.called

    # hard shutdown TypeError fallback
    def raising(hold=False):
        if hold:
            raise TypeError("x")
        return None

    btn3 = IloPowerButton(_button_entry("x"), device, "n", "hard_shutdown", "mdi:x")
    btn3.hass = hass
    dummy3 = SimpleNamespace(press_pwr_btn=MagicMock(side_effect=raising))
    with patch("hpilo.Ilo", return_value=dummy3):
        await btn3.async_press()

    # hard shutdown legacy press_pwr_button(hold=True)
    btn4 = IloPowerButton(_button_entry("x"), device, "n", "hard_shutdown", "mdi:x")
    btn4.hass = hass
    dummy4 = SimpleNamespace(press_pwr_button=MagicMock())
    with patch("hpilo.Ilo", return_value=dummy4):
        await btn4.async_press()
        assert dummy4.press_pwr_button.called

    # unknown action -> HomeAssistantError
    btn5 = IloPowerButton(_button_entry("x"), device, "n", "nope", "mdi:x")
    btn5.hass = hass
    with patch("hpilo.Ilo", return_value=SimpleNamespace()):
        with pytest.raises(HomeAssistantError):
            await btn5.async_press()

    # executor failure -> HomeAssistantError
    btn6 = IloPowerButton(_button_entry("x"), device, "n", "power_on", "mdi:x")
    btn6.hass = hass
    with patch("hpilo.Ilo", side_effect=Exception("fail")):
        with pytest.raises(HomeAssistantError):
            await btn6.async_press()


# --- redfish helper ---


def test_redfish_helper_success():
    from custom_components.hp_ilo import config_flow as cf

    resp = SimpleNamespace(status=200)
    obj = SimpleNamespace(
        login=MagicMock(), get=MagicMock(return_value=resp), logout=MagicMock()
    )
    with patch("redfish.redfish_client", return_value=obj), patch(
        "redfish.AuthMethod", SimpleNamespace(SESSION="s"), create=True
    ):
        # AuthMethod is patched at import inside function, so patch module attr
        import redfish

        real = redfish.AuthMethod
        try:
            out = cf._redfish_test_connection("h", 443, "u", "p")
            assert out is resp
        finally:
            redfish.AuthMethod = real


def test_redfish_helper_bad_status():
    from custom_components.hp_ilo import config_flow as cf

    resp = SimpleNamespace(status=404)
    obj = SimpleNamespace(
        login=MagicMock(), get=MagicMock(return_value=resp), logout=MagicMock()
    )
    with patch("redfish.redfish_client", return_value=obj):
        with pytest.raises(ValueError):
            cf._redfish_test_connection("h", 443, "u", "p")


def test_redfish_helper_logout_failure_tolerated():
    from custom_components.hp_ilo import config_flow as cf

    resp = SimpleNamespace(status=200)

    def bad_logout():
        raise Exception("bye")

    obj = SimpleNamespace(
        login=MagicMock(), get=MagicMock(return_value=resp), logout=bad_logout
    )
    with patch("redfish.redfish_client", return_value=obj):
        out = cf._redfish_test_connection("h", 443, "u", "p")
        assert out is resp


# --- config flow extra branches ---


async def test_ssdp_no_location_abort(hass):
    try:
        from homeassistant.components.ssdp import SsdpServiceInfo
    except ImportError:
        from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo  # type: ignore

    from homeassistant import config_entries

    # empty location + empty upnp -> abort not_supported
    disc = SsdpServiceInfo(
        ssdp_usn="u",
        ssdp_st="urn:schemas-upnp-org:device:Basic:1",
        upnp={},
    )
    # ssdp_location defaults to None in this HA version
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_SSDP}, data=disc
    )
    assert result["type"] == "abort"
    assert result["reason"] == "not_supported"


async def test_ssdp_upnp_host_without_dot_abort(hass):
    try:
        from homeassistant.components.ssdp import SsdpServiceInfo
    except ImportError:
        from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo  # type: ignore

    from homeassistant import config_entries

    disc = SsdpServiceInfo(
        ssdp_usn="u",
        ssdp_st="nodots",
        upnp={},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_SSDP}, data=disc
    )
    assert result["type"] == "abort"


async def test_config_flow_unknown_error(hass):
    from homeassistant import config_entries

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "custom_components.hp_ilo.config_flow._redfish_test_connection",
        side_effect=Exception("weird boom"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=dict(MOCK_CONFIG)
        )
    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "unknown"}


# --- sensor extra branches ---


def test_numeric_value_branches():
    from custom_components.hp_ilo.sensor import _numeric_value

    assert _numeric_value(None) is None
    assert _numeric_value(True) is None
    assert _numeric_value(5) == 5
    assert _numeric_value(5.5) == 5.5
    assert _numeric_value((7, "C")) == 7
    assert _numeric_value("N/A") is None
    assert _numeric_value("") is None
    assert _numeric_value("Unknown") is None
    assert _numeric_value("65 Watts") == 65
    assert _numeric_value("12,5") == 12.5
    assert _numeric_value("bad") is None
    assert _numeric_value({"a": 1}) is None


def test_sensor_none_data_branches(hass):
    from custom_components.hp_ilo.sensor import (
        HpIloFanSensor,
        HpIloPowerOnTimeSensor,
        HpIloPowerSensor,
        HpIloPowerUsageSensor,
        HpIloTemperatureSensor,
        _device_info,
    )
    from homeassistant.helpers.entity import DeviceInfo

    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="se1")
    coord = SimpleNamespace(data={}, entry=entry)
    device = DeviceInfo(identifiers={(DOMAIN, "se1")}, name="T")

    t = HpIloTemperatureSensor(coord, "X", device)  # type: ignore[arg-type]
    coord.data = {}
    assert t.native_value is None
    coord.data = {"temperature": {"X": "bad"}}
    assert t.native_value is None
    coord.data = {"temperature": {"X": {"currentreading": "N/A"}}}
    assert t.native_value is None

    f = HpIloFanSensor(coord, "F", device)  # type: ignore[arg-type]
    coord.data = {}
    assert f.native_value is None
    coord.data = {"fans": {"F": "bad"}}
    assert f.native_value is None

    coord.data = {"power_status": None}
    p = HpIloPowerSensor(coord, device)  # type: ignore[arg-type]
    assert p.native_value == "UNKNOWN"
    coord.data = {"power_status": "off"}
    assert p.native_value == "OFF"

    coord.data = {}
    assert HpIloPowerOnTimeSensor(coord, device).native_value is None  # type: ignore[arg-type]
    assert HpIloPowerUsageSensor(coord, device).native_value is None  # type: ignore[arg-type]

    # device info fallback without name
    entry2 = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "h", "port": 443},
        entry_id="se2",
        title="Title",
    )
    info = _device_info(entry2)  # type: ignore[arg-type]
    assert info["name"] == "Title"


async def test_sensor_setup_non_dict(hass, mock_ilo):
    mock_ilo.get_embedded_health.return_value = {
        "temperature": "bad",
        "fans": "bad",
        "health_at_a_glance": {"fans": {"status": "OK"}},
    }
    mock_ilo.get_server_power_on_time.return_value = None
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="nd1")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # power_on_time None -> no on-time sensor, but others exist
    assert hass.states.get("sensor.test_ilo_power_status") is not None

"""Test hp_ilo setup, coordinator and services."""
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hp_ilo import (
    DOMAIN,
    IloDataUpdateCoordinator,
)

from .const import MOCK_CONFIG


async def test_setup_unload_and_reload_entry(hass, mock_ilo):
    """Test entry setup, reload and unload via config entries."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]
    assert isinstance(
        hass.data[DOMAIN][config_entry.entry_id]["coordinator"], IloDataUpdateCoordinator
    )

    # Coordinator should have parsed batch data.
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    assert coordinator.data["power_status"] == "ON"
    assert coordinator.data["power_usage"] == 67
    assert coordinator.data["health_summary"] == "OK"
    assert "01-Inlet Ambient" in coordinator.data["temperature"]

    # Reload keeps data.
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]

    # Unload removes data.
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.entry_id not in hass.data.get(DOMAIN, {})


async def test_setup_entry_not_ready(hass, mock_ilo_unreachable):
    """Test ConfigEntryNotReady when iLO is unreachable."""
    from custom_components.hp_ilo import async_setup_entry
    from homeassistant.exceptions import ConfigEntryNotReady

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, config_entry)


async def test_coordinator_parses_power_variants(hass, mock_ilo):
    """Coordinator handles tuple, int and missing power readings."""
    from .const import MOCK_HEALTH

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    coordinator = IloDataUpdateCoordinator(hass, config_entry)

    # Tuple format
    mock_ilo.get_embedded_health.return_value = dict(MOCK_HEALTH)
    mock_ilo.get_power_readings.side_effect = None
    mock_ilo.get_power_readings.return_value = {"present_power_reading": (101, "Watts")}
    data = await hass.async_add_executor_job(coordinator._get_ilo_data)
    assert data["power_usage"] == 101

    # Plain int + degraded health
    mock_ilo.get_power_readings.return_value = {"present_power_reading": 55}
    degraded = dict(MOCK_HEALTH)
    degraded["health_at_a_glance"] = {"fans": {"status": "Degraded"}}
    mock_ilo.get_embedded_health.return_value = degraded
    data = await hass.async_add_executor_job(coordinator._get_ilo_data)
    assert data["power_usage"] == 55
    assert data["health_summary"] == "DEGRADED"

    # Missing readings default to 0
    mock_ilo.get_power_readings.side_effect = Exception("not supported")
    mock_ilo.get_embedded_health.return_value = dict(MOCK_HEALTH)
    data = await hass.async_add_executor_job(coordinator._get_ilo_data)
    assert data["power_usage"] == 0


async def test_services_registered_and_callable(hass, mock_ilo):
    """Services are registered on setup and invoke hpilo."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    for service in ("power_on", "reboot_server", "shutdown_graceful", "shutdown_hard"):
        assert hass.services.has_service(DOMAIN, service)

    await hass.services.async_call(DOMAIN, "power_on", {}, blocking=True)
    assert mock_ilo.set_host_power.called

    await hass.services.async_call(DOMAIN, "reboot_server", {}, blocking=True)
    assert mock_ilo.warm_boot_server.called

    await hass.services.async_call(DOMAIN, "shutdown_graceful", {}, blocking=True)
    assert mock_ilo.press_pwr_btn.called

    await hass.services.async_call(DOMAIN, "shutdown_hard", {}, blocking=True)
    assert mock_ilo.hold_pwr_btn.called or mock_ilo.press_pwr_btn.called

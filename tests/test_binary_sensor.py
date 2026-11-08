"""Test hp_ilo binary sensor."""
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hp_ilo import DOMAIN


async def test_health_ok_is_off(hass, mock_ilo):
    """OK health means the problem sensor is off."""
    from .const import MOCK_CONFIG

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.test_ilo_global_health")
    assert state is not None
    assert state.state == "off"
    assert state.attributes.get("status") == "OK"


async def test_health_degraded_is_on(hass, mock_ilo):
    """Degraded health means the problem sensor is on."""
    from .const import MOCK_CONFIG, MOCK_HEALTH

    degraded = dict(MOCK_HEALTH)
    degraded["health_at_a_glance"] = {"fans": {"status": "Critical"}}
    mock_ilo.get_embedded_health.return_value = degraded

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.test_ilo_global_health")
    assert state is not None
    assert state.state == "on"

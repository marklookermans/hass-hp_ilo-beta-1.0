"""Test hp_ilo sensors."""
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hp_ilo import DOMAIN


async def test_sensors_created_with_values(hass, mock_ilo):
    """Sensors are created from coordinator data with correct values."""
    from .const import MOCK_CONFIG

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    all_sensors = hass.states.async_all("sensor")
    assert len(all_sensors) >= 5

    power = hass.states.get("sensor.test_ilo_power_status")
    assert power is not None
    assert power.state == "ON"

    usage = hass.states.get("sensor.test_ilo_power_usage")
    assert usage is not None
    assert usage.state == "67"

    on_time = hass.states.get("sensor.test_ilo_power_on_time")
    assert on_time is not None


async def test_sensor_handles_not_installed(hass, mock_ilo):
    """Not Installed temperatures are skipped."""
    from .const import MOCK_CONFIG

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test2")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    # The "Not-Installed" label must not produce an entity.
    for state in hass.states.async_all("sensor"):
        assert "not-installed" not in state.entity_id.lower()

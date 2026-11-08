"""Test hp_ilo buttons."""
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hp_ilo import DOMAIN


async def test_buttons_created_and_press(hass, mock_ilo):
    """Buttons exist and call the right hpilo methods."""
    from .const import MOCK_CONFIG

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    buttons = hass.states.async_all("button")
    assert len(buttons) == 4

    # Press all buttons to cover every modern hpilo branch.
    for entity_id in [b.entity_id for b in buttons]:
        await hass.services.async_call(
            "button", "press", {"entity_id": entity_id}, blocking=True
        )
        await hass.async_block_till_done()
    assert mock_ilo.set_host_power.called
    assert mock_ilo.warm_boot_server.called
    assert mock_ilo.press_pwr_btn.called
    assert mock_ilo.hold_pwr_btn.called

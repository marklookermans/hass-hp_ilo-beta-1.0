"""Support for HP iLO power buttons."""
from __future__ import annotations

import logging

import hpilo
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the iLO buttons."""
    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
        name=entry.data.get(CONF_NAME) or entry.title or "HP iLO",
        manufacturer="Hewlett Packard Enterprise",
        model="ProLiant (iLO)",
        configuration_url=f"https://{entry.data.get(CONF_HOST)}",
    )

    async_add_entities(
        [
            IloPowerButton(entry, device_info, "Power On", "power_on", "mdi:power-on"),
            IloPowerButton(entry, device_info, "Reboot (Warm)", "warm_boot", "mdi:restart"),
            IloPowerButton(
                entry, device_info, "Shutdown (Graceful)", "press_pwr_btn", "mdi:power"
            ),
            IloPowerButton(
                entry,
                device_info,
                "Shutdown (Hard - Press & Hold)",
                "hard_shutdown",
                "mdi:power-off",
            ),
        ]
    )


class IloPowerButton(ButtonEntity):
    """Representation of an iLO power action button."""

    def __init__(
        self, entry: ConfigEntry, device_info: DeviceInfo, name: str, action_type: str, icon: str
    ) -> None:
        self._entry = entry
        self._action_type = action_type
        base = device_info.get("name", "HP iLO")
        self._attr_name = f"{base} {name}"
        self._attr_unique_id = f"{entry.entry_id}_{action_type}"
        self._attr_device_info = device_info
        self._attr_icon = icon

    def _run_action(self) -> None:
        """Run the hpilo action (executed in the executor)."""
        ilo = hpilo.Ilo(
            hostname=self._entry.data[CONF_HOST],
            login=self._entry.data[CONF_USERNAME],
            password=self._entry.data[CONF_PASSWORD],
            port=self._entry.data.get(CONF_PORT, DEFAULT_PORT),
        )
        if self._action_type == "power_on":
            ilo.set_host_power(True)
        elif self._action_type == "warm_boot":
            if hasattr(ilo, "warm_boot_server"):
                ilo.warm_boot_server()
            else:
                ilo.warm_boot()  # type: ignore[attr-defined]
        elif self._action_type == "press_pwr_btn":
            if hasattr(ilo, "press_pwr_btn"):
                ilo.press_pwr_btn()
            else:
                ilo.press_pwr_button()  # type: ignore[attr-defined]
        elif self._action_type == "hard_shutdown":
            if hasattr(ilo, "hold_pwr_btn"):
                ilo.hold_pwr_btn()
            elif hasattr(ilo, "press_pwr_btn"):
                try:
                    ilo.press_pwr_btn(hold=True)  # type: ignore[call-arg]
                except TypeError:
                    ilo.press_pwr_btn()
            else:
                ilo.press_pwr_button(hold=True)  # type: ignore[attr-defined]
        else:
            raise ValueError(f"Unknown iLO action: {self._action_type}")

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.hass.async_add_executor_job(self._run_action)
        except Exception as err:
            raise HomeAssistantError(f"iLO action failed: {err}") from err

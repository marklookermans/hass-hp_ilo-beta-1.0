"""Support for HP iLO binary sensors."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import IloDataUpdateCoordinator
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the iLO binary sensors."""
    coordinator: IloDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
        name=entry.data.get(CONF_NAME) or entry.title or "HP iLO",
        manufacturer="Hewlett Packard Enterprise",
        model="ProLiant (iLO)",
        configuration_url=f"https://{entry.data.get(CONF_HOST)}",
    )

    async_add_entities([HpIloHealthBinarySensor(coordinator, device_info)])


class HpIloHealthBinarySensor(
    CoordinatorEntity[IloDataUpdateCoordinator], BinarySensorEntity
):
    """Global iLO health: on = problem detected."""

    def __init__(
        self, coordinator: IloDataUpdateCoordinator, device_info: DeviceInfo
    ) -> None:
        super().__init__(coordinator)
        base = device_info.get("name", "HP iLO")
        self._attr_name = f"{base} Global Health"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_global_health"
        self._attr_device_info = device_info
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool:
        """Return True when health is not OK."""
        data = self.coordinator.data or {}
        status = str(data.get("health_summary", "OK")).upper()
        return status not in ("OK", "HEALTHY", "UNKNOWN", "")

    @property
    def extra_state_attributes(self) -> dict:
        """Expose raw health status."""
        data = self.coordinator.data or {}
        return {
            "status": data.get("health_summary", "Unknown"),
            "health_at_a_glance": data.get("health_at_a_glance", {}),
        }

"""Support for HP iLO sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfTime,
)

try:  # HA >= 2022.11
    from homeassistant.const import UnitOfPower as UnitOfElectricPower
except ImportError:  # pragma: no cover - very old HA
    from homeassistant.const import UnitOfElectricPower  # type: ignore[no-redef]
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import IloDataUpdateCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
        name=entry.data.get(CONF_NAME) or entry.title or "HP iLO",
        manufacturer="Hewlett Packard Enterprise",
        model="ProLiant (iLO)",
        configuration_url=f"https://{entry.data[CONF_HOST]}",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the HP iLO sensors from a config entry."""
    coordinator: IloDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = _device_info(entry)
    data = coordinator.data or {}

    sensors: list[SensorEntity] = []

    # 1. Temperature sensors
    temperatures = data.get("temperature") or {}
    if isinstance(temperatures, dict):
        for label, sensor_info in temperatures.items():
            if isinstance(sensor_info, dict) and sensor_info.get("status") == "Not Installed":
                continue
            sensors.append(HpIloTemperatureSensor(coordinator, label, device_info))

    # 2. Fan sensors
    fans = data.get("fans") or {}
    if isinstance(fans, dict):
        for label in fans:
            sensors.append(HpIloFanSensor(coordinator, label, device_info))

    # 3. Power status
    sensors.append(HpIloPowerSensor(coordinator, device_info))

    # 4. Power-on time (only if the iLO reported it)
    if data.get("power_on_time") is not None:
        sensors.append(HpIloPowerOnTimeSensor(coordinator, device_info))

    # 5. Present power usage in Watts
    sensors.append(HpIloPowerUsageSensor(coordinator, device_info))

    async_add_entities(sensors)


def _numeric_value(raw: Any) -> float | int | None:
    """Unpack hpilo (value, unit) tuples to a plain number."""
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)) and raw:
        raw = raw[0]
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if text in ("N/A", "", "Unknown", "UNKNOWN"):
            return None
        try:
            # Handle "65 Watts" style strings.
            first = text.split()[0].replace(",", ".")
            number: float = float(first)
            return int(number) if number.is_integer() else number
        except (ValueError, IndexError):
            return None
    return None


class HpIloBaseSensor(CoordinatorEntity[IloDataUpdateCoordinator], SensorEntity):
    """Base for iLO sensors."""

    def __init__(
        self, coordinator: IloDataUpdateCoordinator, device_info: DeviceInfo
    ) -> None:
        super().__init__(coordinator)
        self._attr_device_info = device_info


class HpIloTemperatureSensor(HpIloBaseSensor):
    """Temperature sensor."""

    def __init__(
        self, coordinator: IloDataUpdateCoordinator, label: str, device_info: DeviceInfo
    ) -> None:
        super().__init__(coordinator, device_info)
        safe = str(label).replace(" ", "_")
        base = device_info.get("name", "HP iLO")
        self._label = label
        self._attr_name = f"{base} Temp {label}"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_temp_{safe}"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        data = (self.coordinator.data or {}).get("temperature", {}) or {}
        temp_data = data.get(self._label)
        if not isinstance(temp_data, dict):
            return None
        value = _numeric_value(temp_data.get("currentreading"))
        return float(value) if value is not None else None


class HpIloFanSensor(HpIloBaseSensor):
    """Fan speed sensor."""

    def __init__(
        self, coordinator: IloDataUpdateCoordinator, label: str, device_info: DeviceInfo
    ) -> None:
        super().__init__(coordinator, device_info)
        safe = str(label).replace(" ", "_")
        base = device_info.get("name", "HP iLO")
        self._label = label
        self._attr_name = f"{base} Fan {label}"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_fan_{safe}"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_icon = "mdi:fan"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        data = (self.coordinator.data or {}).get("fans", {}) or {}
        fan_data = data.get(self._label)
        if not isinstance(fan_data, dict):
            return None
        value = _numeric_value(fan_data.get("speed"))
        return int(value) if value is not None else None


class HpIloPowerSensor(HpIloBaseSensor):
    """Power status sensor."""

    def __init__(
        self, coordinator: IloDataUpdateCoordinator, device_info: DeviceInfo
    ) -> None:
        super().__init__(coordinator, device_info)
        base = device_info.get("name", "HP iLO")
        self._attr_name = f"{base} Power Status"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_power_status"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_options = ["ON", "OFF", "UNKNOWN"]

    @property
    def native_value(self) -> str:
        status = (self.coordinator.data or {}).get("power_status", "UNKNOWN")
        text = str(status or "UNKNOWN").upper()
        return text if text in ("ON", "OFF") else "UNKNOWN"


class HpIloPowerOnTimeSensor(HpIloBaseSensor):
    """Minutes since the server was powered on."""

    def __init__(
        self, coordinator: IloDataUpdateCoordinator, device_info: DeviceInfo
    ) -> None:
        super().__init__(coordinator, device_info)
        base = device_info.get("name", "HP iLO")
        self._attr_name = f"{base} Power On Time"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_power_on_time"
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_icon = "mdi:clock-outline"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        value = _numeric_value((self.coordinator.data or {}).get("power_on_time"))
        return int(value) if value is not None else None


class HpIloPowerUsageSensor(HpIloBaseSensor):
    """Present power draw in Watts."""

    def __init__(
        self, coordinator: IloDataUpdateCoordinator, device_info: DeviceInfo
    ) -> None:
        super().__init__(coordinator, device_info)
        base = device_info.get("name", "HP iLO")
        self._attr_name = f"{base} Power Usage"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_power_usage"
        self._attr_native_unit_of_measurement = UnitOfElectricPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        value = _numeric_value((self.coordinator.data or {}).get("power_usage"))
        return int(value) if value is not None else None

"""The HP Integrated Lights-Out (iLO) component."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import hpilo
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BUTTON, Platform.BINARY_SENSOR]

SCAN_INTERVAL = timedelta(seconds=30)

SERVICE_POWER_ON = "power_on"
SERVICE_REBOOT = "reboot_server"
SERVICE_SHUTDOWN_GRACEFUL = "shutdown_graceful"
SERVICE_SHUTDOWN_HARD = "shutdown_hard"

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Optional(CONF_HOST): cv.string,
    }
)


def _get_ilo_client(entry: ConfigEntry) -> hpilo.Ilo:
    """Create an hpilo client for a config entry (sync, no I/O)."""
    return hpilo.Ilo(
        hostname=entry.data[CONF_HOST],
        login=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
    )


def _parse_power_wattage(power_readings: Any) -> int:
    """Extract present power reading as int watts from get_power_readings()."""
    if not isinstance(power_readings, dict):
        return 0
    present = power_readings.get("present_power_reading")
    if present is None:
        return 0
    # Format is typically (value, "Watts") or a plain number/string.
    if isinstance(present, (list, tuple)) and present:
        value = present[0]
    else:
        value = present
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(str(value).split()[0]))
        except (TypeError, ValueError):
            return 0


def _summarise_health(health: dict) -> str:
    """Reduce health_at_a_glance dict to a single status string."""
    glance = health.get("health_at_a_glance", {})
    if not isinstance(glance, dict):
        return "OK"
    statuses = []
    for _key, val in glance.items():
        if isinstance(val, dict):
            status = str(val.get("status", "OK")).upper()
        else:
            status = str(val).upper()
        statuses.append(status)
    if not statuses:
        return "OK"
    # Worst status wins: anything not OK/HEALTHY is reported.
    for status in statuses:
        if status not in ("OK", "HEALTHY"):
            return status
    return "OK"


class IloDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Central coordinator that fetches all iLO data in one batch."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        try:
            super().__init__(
                hass,
                _LOGGER,
                config_entry=entry,
                name=f"{DOMAIN}_{entry.data[CONF_HOST]}",
                update_interval=SCAN_INTERVAL,
            )
        except TypeError:  # pragma: no cover - HA < 2024.11
            super().__init__(
                hass,
                _LOGGER,
                name=f"{DOMAIN}_{entry.data[CONF_HOST]}",
                update_interval=SCAN_INTERVAL,
            )
        self.entry = entry

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all data in one executor job."""
        return await self.hass.async_add_executor_job(self._get_ilo_data)

    def _get_ilo_data(self) -> dict[str, Any]:
        try:
            ilo = _get_ilo_client(self.entry)
            health = ilo.get_embedded_health() or {}
            try:
                power_readings = ilo.get_power_readings()
            except Exception:  # Power readings are optional (older iLOs)
                _LOGGER.debug(
                    "Power readings unavailable for %s",
                    self.entry.data[CONF_HOST],
                )
                power_readings = {}
            try:
                power_status = ilo.get_host_power_status()
            except Exception:
                power_status = "UNKNOWN"
            try:
                power_on_time = ilo.get_server_power_on_time()
            except Exception:
                power_on_time = None

            return {
                "temperature": health.get("temperature", {}) or {},
                "fans": health.get("fans", {}) or {},
                "power_status": power_status,
                "power_on_time": power_on_time,
                "power_usage": _parse_power_wattage(power_readings),
                "power_readings": power_readings if isinstance(power_readings, dict) else {},
                "health_summary": _summarise_health(health),
                "health_at_a_glance": health.get("health_at_a_glance", {}) or {},
            }
        except Exception as err:
            raise UpdateFailed(f"Communication error: {err}") from err


async def _async_handle_power_action(hass: HomeAssistant, entry: ConfigEntry, service: str) -> None:
    """Execute a power action for a given entry in the executor."""
    ilo = _get_ilo_client(entry)

    def _run() -> None:
        if service == SERVICE_REBOOT:
            # python-hpilo: warm_boot_server(); tolerate legacy alias warm_boot.
            if hasattr(ilo, "warm_boot_server"):
                ilo.warm_boot_server()
            else:
                ilo.warm_boot()  # type: ignore[attr-defined]
        elif service == SERVICE_SHUTDOWN_GRACEFUL:
            # Momentary press == graceful shutdown / power on if off.
            if hasattr(ilo, "press_pwr_btn"):
                ilo.press_pwr_btn()
            else:
                ilo.press_pwr_button()  # type: ignore[attr-defined]
        elif service == SERVICE_SHUTDOWN_HARD:
            # Press & hold == forced power off.
            if hasattr(ilo, "hold_pwr_btn"):
                ilo.hold_pwr_btn()
            elif hasattr(ilo, "press_pwr_btn"):
                try:
                    ilo.press_pwr_btn(hold=True)  # type: ignore[call-arg]
                except TypeError:
                    ilo.press_pwr_btn()
            else:
                ilo.press_pwr_button(hold=True)  # type: ignore[attr-defined]
        elif service == SERVICE_POWER_ON:
            ilo.set_host_power(True)

    await hass.async_add_executor_job(_run)
    _LOGGER.info("iLO action %s successful on %s", service, entry.data[CONF_HOST])


def _resolve_entry(hass: HomeAssistant, call: ServiceCall) -> ConfigEntry | None:
    """Resolve target config entry from service data (entry_id or host)."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return None
    entry_id = call.data.get("entry_id")
    if entry_id:
        for entry in entries:
            if entry.entry_id == entry_id:
                return entry
        return None
    host = call.data.get(CONF_HOST)
    if host:
        for entry in entries:
            if entry.data.get(CONF_HOST) == host:
                return entry
        return None
    # Default to the (first) configured entry for backwards compatibility.
    return entries[0]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the HP iLO component (services only; entries use config flow)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HP iLO from a config entry."""
    coordinator = IloDataUpdateCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Unable to connect to iLO: {err}") from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "entry": entry,
    }

    async def handle_power_action(call: ServiceCall) -> None:
        target = _resolve_entry(hass, call)
        if target is None:
            _LOGGER.error("iLO service %s called with no matching entry", call.service)
            return
        try:
            await _async_handle_power_action(hass, target, call.service)
        except Exception as err:
            _LOGGER.error("Error executing %s: %s", call.service, err)

    # Register services once (shared across entries).
    if not hass.services.has_service(DOMAIN, SERVICE_POWER_ON):
        for service in (
            SERVICE_REBOOT,
            SERVICE_SHUTDOWN_GRACEFUL,
            SERVICE_SHUTDOWN_HARD,
            SERVICE_POWER_ON,
        ):
            hass.services.async_register(DOMAIN, service, handle_power_action, schema=SERVICE_SCHEMA)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        # Remove shared services when the last entry is unloaded.
        if not hass.data.get(DOMAIN):
            for service in (
                SERVICE_REBOOT,
                SERVICE_SHUTDOWN_GRACEFUL,
                SERVICE_SHUTDOWN_HARD,
                SERVICE_POWER_ON,
            ):
                if hass.services.has_service(DOMAIN, service):
                    hass.services.async_remove(DOMAIN, service)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)

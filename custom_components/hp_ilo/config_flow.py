"""Config flow for HP iLO via Redfish API."""
from __future__ import annotations

import logging
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.data_entry_flow import FlowResult

try:  # HA >= 2023.x
    from homeassistant.components.ssdp import SsdpServiceInfo
except ImportError:  # pragma: no cover - very old HA
    from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo  # type: ignore[no-redef]

from .const import DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _redfish_test_connection(host: str, port: int, username: str, password: str):
    """Test a Redfish connection (blocking). Raises on failure."""
    from redfish import AuthMethod, redfish_client

    base_url = f"https://{host}:{port}"
    redfish_obj = redfish_client(
        base_url=base_url,
        username=username,
        password=password,
        default_prefix="/redfish/v1/",
        timeout=10,
    )
    try:
        redfish_obj.login(auth=AuthMethod.SESSION)
        response = redfish_obj.get("/redfish/v1/")
        status = getattr(response, "status", None)
        if status != 200:
            raise ValueError(f"Redfish request failed with status {status}")
        return response
    finally:
        try:
            redfish_obj.logout()
        except Exception:  # noqa: BLE001 - best effort logout
            pass


class RedfishIloFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for HP iLO via Redfish."""

    VERSION = 1

    def __init__(self) -> None:
        self._config: dict = {}

    # ------------------------------------------------------------------
    # SSDP DISCOVERY
    # ------------------------------------------------------------------
    async def async_step_ssdp(self, discovery_info: SsdpServiceInfo) -> FlowResult:
        """Handle SSDP discovery from an iLO.

        iLOs announce as Basic:1; not all announcements contain the word
        'redfish', so we accept any reachable location and validate later.
        """
        location = getattr(discovery_info, "ssdp_location", None) or ""
        parsed = urlparse(location) if location else None
        host = parsed.hostname if parsed and parsed.hostname else None
        if not host:
            # Fall back to UPnP friendly fields when location is missing.
            upnp = getattr(discovery_info, "upnp", None) or {}
            host = (
                upnp.get("X-Actual-Host")
                or getattr(discovery_info, "ssdp_st", None)
            )
            if not host or "." not in str(host):
                return self.async_abort(reason="not_supported")

        port = parsed.port if parsed and parsed.port else DEFAULT_PORT

        self._config = {
            CONF_HOST: host,
            CONF_PORT: int(port),
            CONF_NAME: f"HP iLO @ {host}",
        }

        self.context["configuration_url"] = f"https://{host}:{port}"
        await self.async_set_unique_id(f"{DOMAIN}_{host}")
        self._abort_if_unique_id_configured(updates=self._config)

        return await self.async_step_user()

    # ------------------------------------------------------------------
    # MANUAL INPUT
    # ------------------------------------------------------------------
    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle manual entry of host, port and credentials."""
        errors: dict = {}

        if user_input is not None:
            self._config = {
                CONF_HOST: str(user_input[CONF_HOST]).strip(),
                CONF_PORT: int(user_input[CONF_PORT]),
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                CONF_NAME: user_input.get(CONF_NAME)
                or f"HP iLO @ {str(user_input[CONF_HOST]).strip()}",
            }
            return await self.async_step_auth()

        default_host = self._config.get(CONF_HOST, "")
        default_port = self._config.get(CONF_PORT, DEFAULT_PORT)
        default_name = self._config.get(CONF_NAME, "")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=default_host): str,
                    vol.Required(CONF_PORT, default=default_port): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                    vol.Required(CONF_USERNAME, default="Administrator"): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_NAME, default=default_name): str,
                }
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # AUTHENTICATION & CONNECTION TEST
    # ------------------------------------------------------------------
    async def async_step_auth(self, user_input: dict | None = None) -> FlowResult:
        """Validate credentials against the Redfish API root."""
        errors: dict = {}

        try:
            await self.hass.async_add_executor_job(
                _redfish_test_connection,
                self._config[CONF_HOST],
                int(self._config[CONF_PORT]),
                self._config[CONF_USERNAME],
                self._config[CONF_PASSWORD],
            )
        except Exception as err:  # noqa: BLE001
            err_str = str(err).lower()
            _LOGGER.error("Redfish error during setup for %s: %s", self._config.get(CONF_HOST), err)
            if "timeout" in err_str or "connection" in err_str or "connect" in err_str:
                errors["base"] = "cannot_connect"
            elif (
                "401" in err_str
                or "unauthorized" in err_str
                or "forbidden" in err_str
                or "auth" in err_str
            ):
                errors["base"] = "invalid_auth"
            else:
                errors["base"] = "unknown"

            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_HOST, default=self._config.get(CONF_HOST, "")): str,
                        vol.Required(CONF_PORT, default=self._config.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                            vol.Coerce(int), vol.Range(min=1, max=65535)
                        ),
                        vol.Required(
                            CONF_USERNAME,
                            default=self._config.get(CONF_USERNAME, "Administrator"),
                        ): str,
                        vol.Required(CONF_PASSWORD): str,
                        vol.Optional(CONF_NAME, default=self._config.get(CONF_NAME, "")): str,
                    }
                ),
                errors=errors,
            )

        unique_id = f"{DOMAIN}_{self._config[CONF_HOST]}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(updates=self._config)

        return self.async_create_entry(
            title=self._config[CONF_NAME],
            data=self._config,
        )

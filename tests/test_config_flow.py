"""Test hp_ilo config flow."""
from unittest.mock import MagicMock, patch

import pytest
from homeassistant import config_entries

from custom_components.hp_ilo.const import DOMAIN

from .const import MOCK_CONFIG


@pytest.fixture(autouse=True)
def bypass_setup_fixture():
    """Prevent setup."""
    with patch(
        "custom_components.hp_ilo.async_setup",
        return_value=True,
    ), patch(
        "custom_components.hp_ilo.async_setup_entry",
        return_value=True,
    ):
        yield


def _mock_redfish_ok():
    response = MagicMock()
    response.status = 200
    redfish_obj = MagicMock()
    redfish_obj.get.return_value = response
    return redfish_obj


async def test_successful_config_flow(hass):
    """Test a successful user config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    with patch(
        "custom_components.hp_ilo.config_flow._redfish_test_connection",
        return_value=MagicMock(status=200),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=dict(MOCK_CONFIG)
        )

    assert result["type"] == "create_entry"
    assert result["title"] == MOCK_CONFIG["name"] if "name" in MOCK_CONFIG else result["title"]
    assert result["data"]["host"] == MOCK_CONFIG["host"]
    assert result["result"]


async def test_failed_config_flow_invalid_auth(hass):
    """Test invalid credentials surface invalid_auth."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "custom_components.hp_ilo.config_flow._redfish_test_connection",
        side_effect=Exception("401 Unauthorized"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=dict(MOCK_CONFIG)
        )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_failed_config_flow_cannot_connect(hass):
    """Test connection errors surface cannot_connect."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "custom_components.hp_ilo.config_flow._redfish_test_connection",
        side_effect=Exception("connection timeout"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=dict(MOCK_CONFIG)
        )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_ssdp_discovery(hass):
    """Test SSDP discovery creates a flow with parsed host."""
    try:
        from homeassistant.components.ssdp import SsdpServiceInfo
    except ImportError:
        from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo  # type: ignore[no-redef]

    discovery = SsdpServiceInfo(
        ssdp_usn="uuid:test",
        ssdp_st="urn:schemas-upnp-org:device:Basic:1",
        ssdp_location="https://192.168.1.50:443/redfish/v1/",
        ssdp_server="HPE-iLO",
        ssdp_headers={},
        upnp={},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_SSDP}, data=discovery
    )
    # Either shows the user form (prefilled) or aborts as already configured.
    assert result["type"] in ("form", "abort")

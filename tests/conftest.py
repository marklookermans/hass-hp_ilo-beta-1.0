"""Global fixtures for hp_ilo integration."""
from unittest.mock import MagicMock, patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture():
    """Skip persistent notification calls."""
    with patch("homeassistant.components.persistent_notification.async_create"), patch(
        "homeassistant.components.persistent_notification.async_dismiss"
    ):
        yield


def _mock_ilo_instance(power_status="ON", power_on_time=1234, health=None):
    """Build a mocked hpilo.Ilo instance."""
    from .const import MOCK_HEALTH

    mock = MagicMock()
    mock.get_embedded_health.return_value = health if health is not None else dict(MOCK_HEALTH)
    mock.get_power_readings.return_value = {"present_power_reading": (67, "Watts")}
    mock.get_host_power_status.return_value = power_status
    mock.get_server_power_on_time.return_value = power_on_time
    # Power actions
    mock.warm_boot_server.return_value = None
    mock.press_pwr_btn.return_value = None
    mock.hold_pwr_btn.return_value = None
    mock.set_host_power.return_value = None
    return mock


@pytest.fixture(name="mock_ilo")
def mock_ilo_fixture():
    """Mock hpilo.Ilo with healthy data (patches the shared hpilo module)."""
    with patch("hpilo.Ilo", autospec=True) as mock_cls:
        instance = _mock_ilo_instance()
        mock_cls.return_value = instance
        yield instance


@pytest.fixture(name="mock_ilo_unreachable")
def mock_ilo_unreachable_fixture():
    """Mock hpilo.Ilo that raises on every call."""
    with patch("hpilo.Ilo", side_effect=Exception("no route to host")):
        yield

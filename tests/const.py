"""Constants for hp_ilo tests."""
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_PORT, CONF_USERNAME

MOCK_CONFIG = {
    CONF_HOST: "192.168.1.100",
    CONF_PORT: 443,
    CONF_USERNAME: "Administrator",
    CONF_PASSWORD: "password123",
    CONF_NAME: "Test iLO",
}

MOCK_HEALTH = {
    "temperature": {
        "01-Inlet Ambient": {
            "label": "01-Inlet Ambient",
            "status": "OK",
            "currentreading": (19, "Celsius"),
            "caution": (42, "Celsius"),
        },
        "02-CPU 1": {
            "label": "02-CPU 1",
            "status": "OK",
            "currentreading": (40, "Celsius"),
        },
        "Not-Installed": {
            "label": "Not-Installed",
            "status": "Not Installed",
            "currentreading": "N/A",
        },
    },
    "fans": {
        "Fan 1": {"label": "Fan 1", "status": "OK", "speed": (22, "Percentage")},
        "Fan 2": {"label": "Fan 2", "status": "OK", "speed": 35},
    },
    "health_at_a_glance": {
        "fans": {"status": "OK"},
        "temperature": {"status": "OK"},
    },
}

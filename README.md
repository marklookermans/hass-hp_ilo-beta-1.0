# HP Integrated Lights-Out (iLO) for Home Assistant 🚀

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![Project Maintenance](https://img.shields.io/badge/maintainer-Mark%20Lookermans-blue.svg)
![Version](https://img.shields.io/badge/version-0.1.2-orange.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

An advanced, high-performance integration for monitoring and managing **HP ProLiant Servers** via iLO 3, 4, and 5. This fork is optimized for stability, speed, and deep Home Assistant integration.

---

## 🌟 Key Improvements

| Feature | Description |
| :--- | :--- |
| **High Frequency** | Real-time monitoring with a default **30-second polling interval**. |
| **Efficient** | Uses a `DataUpdateCoordinator` to fetch data in one batch, reducing iLO CPU load. |
| **Actionable** | Includes **Buttons** and **Services** for power management (Power On, Reboot, Shutdown). |
| **Modern** | Full support for **Config Flow** and **Auto-Discovery** (SSDP & Redfish). |

---

## ⚙️ Deep Dive: Polling & Architecture

Unlike legacy integrations that poll each sensor (CPU, Fans, Power) individually, this component utilizes a **centralized polling architecture**.

### 🔄 DataUpdateCoordinator
To protect the often-limited processing power of the iLO management chip, we implement a `DataUpdateCoordinator`. 

* **The Problem:** In a standard setup with 20 sensors polling every 30s, the iLO would receive 40 requests per minute, often leading to connection timeouts or "iLO Not Responding" errors.
* **The Solution:** Our Coordinator performs **one single batch request** every 30 seconds. It fetches the complete XML/JSON health blob from the iLO, parses it once, and pushes the updates to all 20+ entities simultaneously.



### 🛰️ Communication Methods
The integration automatically switches between communication protocols based on the task:

1.  **Redfish API (iLO 5+):** Used primarily for discovery and modern REST-based telemetry.
2.  **RIBCL via JSON/XML (iLO 3/4):** Used for deep health metrics (fan speeds, specific temp sensors) where Redfish might be limited.
3.  **Raw Socket Communication:** Used via the `python-hpilo` library for low-level power actions like the "Press & Hold" (Hard Shutdown) simulation.

---

## 🚀 Setup & Discovery
Once installed, go to **Settings** → **Devices & Services** → **Add Integration** and search for **HP iLO**.

> [!TIP]
> **Auto-Discovery:** For the best experience, enable **SSDP/Discovery** in your iLO Web Interface. This allows Home Assistant to find your server automatically using the `urn:schemas-upnp-org:device:Basic:1` target.

---

## 📊 Available Entities

### 🌡️ Monitoring (Sensors)
* **Environment:** Detailed temperature readings for CPU, Memory, I/O, and Ambient zones.
* **Cooling:** Fan speed percentages for all system fans.
* **Status:** Current Power State (ON/OFF) and Power-On time.

### ⚡ Control (Buttons)
The integration provides physical buttons on the device page for immediate action:
* **Power On:** Starts the server.
* **Reboot (Warm):** Triggers a warm restart (Soft Reset).
* **Shutdown (Graceful):** Signals the OS to shut down cleanly.
* **Shutdown (Hard):** **Press & Hold** action (simulates 4s button press) via `hold_pwr_btn()` (with `press_pwr_btn` fallbacks).

---

## 🛠 Services
Use these services in your automations or scripts:

| Service | Description |
| :--- | :--- |
| `hp_ilo.power_on` | Power on the server. |
| `hp_ilo.reboot_server` | Perform a warm boot. |
| `hp_ilo.shutdown_graceful` | Clean OS shutdown (Power button press). |
| `hp_ilo.shutdown_hard` | Forced shutdown (Press & Hold). |

---

## 🚧 Roadmap
- [x] Optimization via DataUpdateCoordinator.
- [x] Power Control Buttons (with Press & Hold fix).
- [x] **Binary Sensors:** Global health status (OK/Critical).
- [ ] **Firmware Alerts:** Notifications for new iLO firmware versions.

## Credits
Forked and improved from [chkuendig/hass-hp_ilo-beta](https://github.com/chkuendig/hass-hp_ilo-beta). Originally based on the Home Assistant core component.

## Contributors
- [@marklookermans](https://github.com/marklookermans) — maintainer
- Muse Spark (Codebuff agent) — stability overhaul, 100% test coverage, power-control and discovery fixes




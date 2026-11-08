_HP iLO integration for Home Assistant — monitor and control HPE ProLiant servers via iLO 3/4/5._

**This component will set up the following platforms.**

Platform | Description
-- | --
`sensor` | Temperatures, fan speeds, power status, power-on time and power usage.
`button` | Power on, warm reboot, graceful and hard shutdown.
`binary_sensor` | Global health status (problem = on).

## Configuration is done in the UI

Go to **Settings → Devices & Services → Add Integration** and search for **HP iLO**.
Enter the iLO hostname, port (default 443) and credentials.
Redfish is used to validate the connection; RIBCL (`python-hpilo`) is used for polling and power actions.

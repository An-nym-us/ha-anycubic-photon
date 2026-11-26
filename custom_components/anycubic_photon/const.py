"""Constants for the Anycubic Photon integration."""

DOMAIN = "anycubic_photon"
MANUFACTURER = "Anycubic"

CONF_CONNECTION = "connection"
CONNECTION_LOCAL = "local"
CONNECTION_CLOUD = "cloud"

CONF_AUTH_MODE = "auth_mode"
CONF_TOKEN = "token"
CONF_PRINTER_ID = "printer_id"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = {CONNECTION_LOCAL: 15, CONNECTION_CLOUD: 60}  # seconds
MIN_SCAN_INTERVAL = {CONNECTION_LOCAL: 5, CONNECTION_CLOUD: 30}


def connection_type(data: dict) -> str:
    """Entries made before cloud support have no connection key: they are LAN."""
    return data.get(CONF_CONNECTION, CONNECTION_LOCAL)

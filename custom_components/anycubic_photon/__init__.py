"""Anycubic Photon integration for Home Assistant (LAN or Anycubic Cloud)."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DEFAULT_PORT, PhotonAuthError, PhotonClient, PhotonError
from .cloud import AnycubicCloudClient, CloudPrinter
from .const import (
    CONF_AUTH_MODE,
    CONF_PRINTER_ID,
    CONF_TOKEN,
    CONNECTION_CLOUD,
    connection_type,
)
from .coordinator import PhotonConfigEntry, PhotonCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]


def build_device(hass: HomeAssistant, data: dict) -> PhotonClient | CloudPrinter:
    if connection_type(data) == CONNECTION_CLOUD:
        client = AnycubicCloudClient(
            async_get_clientsession(hass), data[CONF_AUTH_MODE], data[CONF_TOKEN]
        )
        return CloudPrinter(client, int(data[CONF_PRINTER_ID]))
    return PhotonClient(data[CONF_HOST], data.get(CONF_PORT, DEFAULT_PORT))


async def async_setup_entry(hass: HomeAssistant, entry: PhotonConfigEntry) -> bool:
    device = build_device(hass, dict(entry.data))
    try:
        sysinfo = await device.get_sysinfo()
    except PhotonAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except PhotonError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = PhotonCoordinator(hass, entry, device, sysinfo)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PhotonConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: PhotonConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

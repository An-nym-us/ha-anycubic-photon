"""Anycubic Photon (LAN) integration for Home Assistant."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api import DEFAULT_PORT, PhotonClient, PhotonError
from .coordinator import PhotonConfigEntry, PhotonCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: PhotonConfigEntry) -> bool:
    client = PhotonClient(entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT))
    try:
        sysinfo = await client.get_sysinfo()
    except PhotonError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = PhotonCoordinator(hass, entry, client, sysinfo)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PhotonConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: PhotonConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

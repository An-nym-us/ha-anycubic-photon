"""Polling coordinator for the Anycubic Photon integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PhotonClient, PhotonError, PhotonStatus, PhotonSysInfo
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type PhotonConfigEntry = ConfigEntry[PhotonCoordinator]


class PhotonCoordinator(DataUpdateCoordinator[PhotonStatus]):
    """Polls ``getstatus`` on a fixed interval."""

    config_entry: PhotonConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PhotonConfigEntry,
        client: PhotonClient,
        sysinfo: PhotonSysInfo,
    ) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.sysinfo = sysinfo

    async def _async_update_data(self) -> PhotonStatus:
        try:
            return await self.client.get_status()
        except PhotonError as err:
            raise UpdateFailed(str(err)) from err

    async def async_send(self, command: str) -> None:
        """Send a control command, then refresh state right away."""
        await self.client.send(command)
        await self.async_request_refresh()

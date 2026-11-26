"""Polling coordinator for the Anycubic Photon integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Protocol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PhotonAuthError, PhotonError, PhotonStatus, PhotonSysInfo
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, connection_type

_LOGGER = logging.getLogger(__name__)


class PhotonDevice(Protocol):
    """What the coordinator needs: PhotonClient (LAN) and CloudPrinter both fit."""

    async def get_status(self) -> PhotonStatus: ...
    async def pause(self) -> None: ...
    async def resume(self) -> None: ...
    async def stop(self) -> None: ...


type PhotonConfigEntry = ConfigEntry[PhotonCoordinator]


class PhotonCoordinator(DataUpdateCoordinator[PhotonStatus]):
    """Polls the printer's status on a fixed interval."""

    config_entry: PhotonConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PhotonConfigEntry,
        device: PhotonDevice,
        sysinfo: PhotonSysInfo,
    ) -> None:
        default = DEFAULT_SCAN_INTERVAL[connection_type(entry.data)]
        interval = entry.options.get(CONF_SCAN_INTERVAL, default)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.device = device
        self.sysinfo = sysinfo

    async def _async_update_data(self) -> PhotonStatus:
        try:
            return await self.device.get_status()
        except PhotonAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PhotonError as err:
            raise UpdateFailed(str(err)) from err

    async def async_command(self, action: str) -> None:
        """Run pause/resume/stop, then refresh state right away."""
        await getattr(self.device, action)()
        await self.async_request_refresh()

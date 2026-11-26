"""Base entity for the Anycubic Photon integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import PhotonCoordinator


class PhotonEntity(CoordinatorEntity[PhotonCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: PhotonCoordinator, key: str) -> None:
        super().__init__(coordinator)
        info = coordinator.sysinfo
        self._attr_unique_id = f"{info.serial}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, info.serial)},
            manufacturer=MANUFACTURER,
            model=info.model,
            name=info.name or info.model,
            serial_number=info.serial,
            sw_version=info.firmware,
        )

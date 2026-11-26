"""Binary sensors for the Anycubic Photon integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PhotonConfigEntry
from .entity import PhotonEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PhotonConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([PhotonPrintingSensor(entry.runtime_data)])


class PhotonPrintingSensor(PhotonEntity, BinarySensorEntity):
    _attr_translation_key = "printing"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "printing")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.is_printing

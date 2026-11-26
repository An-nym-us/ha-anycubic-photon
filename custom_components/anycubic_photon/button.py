"""Pause / resume / stop buttons for the Anycubic Photon integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import PhotonError
from .coordinator import PhotonConfigEntry
from .entity import PhotonEntity


@dataclass(frozen=True, kw_only=True)
class PhotonButtonDescription(ButtonEntityDescription):
    action: str


BUTTONS: tuple[PhotonButtonDescription, ...] = (
    PhotonButtonDescription(key="pause", translation_key="pause", action="pause"),
    PhotonButtonDescription(key="resume", translation_key="resume", action="resume"),
    PhotonButtonDescription(key="stop", translation_key="stop", action="stop"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PhotonConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(PhotonButton(coordinator, desc) for desc in BUTTONS)


class PhotonButton(PhotonEntity, ButtonEntity):
    entity_description: PhotonButtonDescription

    def __init__(self, coordinator, description: PhotonButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        try:
            await self.coordinator.async_command(self.entity_description.action)
        except PhotonError as err:
            raise HomeAssistantError(
                f"Printer did not accept {self.entity_description.action}: {err}"
            ) from err

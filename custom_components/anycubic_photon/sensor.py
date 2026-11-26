"""Sensors for the Anycubic Photon integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfLength, UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import PhotonStatus
from .const import CONNECTION_LOCAL, connection_type
from .coordinator import PhotonConfigEntry
from .entity import PhotonEntity


@dataclass(frozen=True, kw_only=True)
class PhotonSensorDescription(SensorEntityDescription):
    value_fn: Callable[[PhotonStatus], str | int | float | None]
    printing_only: bool = True
    lan_only: bool = False


SENSORS: tuple[PhotonSensorDescription, ...] = (
    PhotonSensorDescription(
        key="state",
        translation_key="state",
        value_fn=lambda s: s.state,
        printing_only=False,
    ),
    PhotonSensorDescription(
        key="progress",
        translation_key="progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.progress,
    ),
    PhotonSensorDescription(
        key="current_layer",
        translation_key="current_layer",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.current_layer,
    ),
    PhotonSensorDescription(
        key="total_layers",
        translation_key="total_layers",
        value_fn=lambda s: s.total_layers,
    ),
    PhotonSensorDescription(
        key="elapsed_time",
        translation_key="elapsed_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda s: s.elapsed_seconds,
    ),
    PhotonSensorDescription(
        key="remaining_time",
        translation_key="remaining_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda s: s.remaining_seconds,
    ),
    PhotonSensorDescription(
        key="file_name",
        translation_key="file_name",
        value_fn=lambda s: s.file_name,
    ),
    PhotonSensorDescription(
        key="resin_volume",
        translation_key="resin_volume",
        device_class=SensorDeviceClass.VOLUME,
        native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        value_fn=lambda s: s.resin_ml,
        lan_only=True,
    ),
    PhotonSensorDescription(
        key="layer_height",
        translation_key="layer_height",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.layer_height_mm,
        lan_only=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PhotonConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    is_lan = connection_type(entry.data) == CONNECTION_LOCAL
    async_add_entities(
        PhotonSensor(coordinator, desc)
        for desc in SENSORS
        if is_lan or not desc.lan_only
    )


class PhotonSensor(PhotonEntity, SensorEntity):
    entity_description: PhotonSensorDescription

    def __init__(self, coordinator, description: PhotonSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | float | None:
        status = self.coordinator.data
        # Job fields are stale or missing when nothing is printing.
        if self.entity_description.printing_only and not (
            status.is_printing or status.is_paused
        ):
            return None
        return self.entity_description.value_fn(status)

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.key == "state":
            return {"raw_status": ",".join(self.coordinator.data.raw)}
        return None

"""Binary sensor platform for Google Weather integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LOCATION, DOMAIN
from .coordinator import GoogleWeatherCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class GoogleWeatherBinarySensorDescription(BinarySensorEntityDescription):
    """Describes Google Weather binary sensor entity."""

    value_fn: Callable[[dict], bool] | None = None
    attributes_fn: Callable[[dict], dict[str, Any]] | None = None


# Severity levels for filtering
SEVERE_SEVERITIES = ["EXTREME", "SEVERE"]
URGENT_URGENCIES = ["IMMEDIATE", "EXPECTED"]


def has_alerts(data: dict) -> bool:
    """Check if there are any weather alerts."""
    return bool(data.get("weatherAlerts", []))


def has_severe_alerts(data: dict) -> bool:
    """Check if there are severe weather alerts."""
    alerts = data.get("weatherAlerts", [])
    return any(
        alert.get("severity") in SEVERE_SEVERITIES
        for alert in alerts
    )


def has_urgent_alerts(data: dict) -> bool:
    """Check if there are urgent weather alerts."""
    alerts = data.get("weatherAlerts", [])
    return any(
        alert.get("urgency") in URGENT_URGENCIES
        for alert in alerts
    )


def get_alert_attributes(data: dict) -> dict[str, Any]:
    """Get detailed attributes for all alerts."""
    alerts = data.get("weatherAlerts", [])
    if not alerts:
        return {"alert_count": 0}

    alert_details = []
    for alert in alerts:
        alert_info = {
            "alert_id": alert.get("alertId"),
            "title": alert.get("alertTitle", {}).get("text"),
            "event_type": alert.get("eventType"),
            "area": alert.get("areaName"),
            "severity": alert.get("severity"),
            "certainty": alert.get("certainty"),
            "urgency": alert.get("urgency"),
            "start_time": alert.get("startTime"),
            "expiration_time": alert.get("expirationTime"),
            "description": alert.get("description"),
            "instruction": alert.get("instruction"),
        }
        # Filter out None values
        alert_details.append({k: v for k, v in alert_info.items() if v is not None})

    return {
        "alert_count": len(alerts),
        "alerts": alert_details,
        "max_severity": max(
            (alert.get("severity") for alert in alerts if alert.get("severity")),
            default=None,
        ),
        "data_source": alerts[0].get("dataSource", {}).get("name") if alerts else None,
    }


def get_severe_alert_attributes(data: dict) -> dict[str, Any]:
    """Get detailed attributes for severe alerts only."""
    alerts = data.get("weatherAlerts", [])
    severe_alerts = [
        alert for alert in alerts
        if alert.get("severity") in SEVERE_SEVERITIES
    ]

    if not severe_alerts:
        return {"alert_count": 0}

    alert_details = []
    for alert in severe_alerts:
        alert_info = {
            "alert_id": alert.get("alertId"),
            "title": alert.get("alertTitle", {}).get("text"),
            "event_type": alert.get("eventType"),
            "area": alert.get("areaName"),
            "severity": alert.get("severity"),
            "certainty": alert.get("certainty"),
            "urgency": alert.get("urgency"),
            "start_time": alert.get("startTime"),
            "expiration_time": alert.get("expirationTime"),
            "instruction": alert.get("instruction"),
        }
        alert_details.append({k: v for k, v in alert_info.items() if v is not None})

    return {
        "alert_count": len(severe_alerts),
        "alerts": alert_details,
    }


BINARY_SENSOR_TYPES: tuple[GoogleWeatherBinarySensorDescription, ...] = (
    GoogleWeatherBinarySensorDescription(
        key="weather_alert",
        name="Weather Alert",
        device_class=BinarySensorDeviceClass.SAFETY,
        icon="mdi:alert",
        value_fn=has_alerts,
        attributes_fn=get_alert_attributes,
    ),
    GoogleWeatherBinarySensorDescription(
        key="severe_weather_alert",
        name="Severe Weather Alert",
        device_class=BinarySensorDeviceClass.SAFETY,
        icon="mdi:alert-circle",
        value_fn=has_severe_alerts,
        attributes_fn=get_severe_alert_attributes,
    ),
    GoogleWeatherBinarySensorDescription(
        key="urgent_weather_alert",
        name="Urgent Weather Alert",
        device_class=BinarySensorDeviceClass.SAFETY,
        icon="mdi:alert-octagon",
        value_fn=has_urgent_alerts,
        attributes_fn=lambda data: {
            "urgent_alerts": [
                {
                    "title": alert.get("alertTitle", {}).get("text"),
                    "urgency": alert.get("urgency"),
                    "instruction": alert.get("instruction"),
                }
                for alert in data.get("weatherAlerts", [])
                if alert.get("urgency") in URGENT_URGENCIES
            ]
        } if has_urgent_alerts(data) else {},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Google Weather binary sensor entities."""
    coordinator: GoogleWeatherCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Check if alerts are supported for this location
    # The coordinator has already done its first refresh by this point
    if coordinator.alerts_supported is False:
        _LOGGER.info(
            "Skipping binary sensor setup - weather alerts not supported for this location"
        )
        return

    location = entry.data.get(CONF_LOCATION, "home")

    async_add_entities(
        GoogleWeatherBinarySensor(coordinator, entry, description, location)
        for description in BINARY_SENSOR_TYPES
    )


class GoogleWeatherBinarySensor(
    CoordinatorEntity[GoogleWeatherCoordinator], BinarySensorEntity
):
    """Representation of a Google Weather binary sensor."""

    entity_description: GoogleWeatherBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GoogleWeatherCoordinator,
        entry: ConfigEntry,
        description: GoogleWeatherBinarySensorDescription,
        location: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description

        # Use location directly for entity ID (slugified)
        location_slug = location.lower().replace(" ", "_")

        # Create friendly name from location (title case)
        location_name = location.replace("_", " ").title()

        # Set entity name to just the alert type (device name will be prefixed)
        self._attr_name = description.name
        self._attr_unique_id = f"{location_slug}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{entry.entry_id}_warnings")},
            "name": location_name,  # Just the location, not "Location Warnings"
            "manufacturer": "Google",
            "model": "Weather API - Warnings",
            "sw_version": "v1",
            "via_device": (DOMAIN, entry.entry_id),
        }

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        if self.coordinator.data and self.entity_description.value_fn:
            return self.entity_description.value_fn(self.coordinator.data)
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if self.coordinator.data and self.entity_description.attributes_fn:
            return self.entity_description.attributes_fn(self.coordinator.data)
        return {}

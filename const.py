"""Constants for the Google Weather integration."""
from datetime import timedelta

DOMAIN = "google_weather"

# Configuration
CONF_LOCATION = "location"
CONF_PREFIX = "prefix"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_UNIT_SYSTEM = "unit_system"

# Defaults
DEFAULT_PREFIX = "gw"
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=15)
DEFAULT_UNIT_SYSTEM = "METRIC"

# Unit systems
UNIT_SYSTEM_METRIC = "METRIC"
UNIT_SYSTEM_IMPERIAL = "IMPERIAL"
UNIT_SYSTEMS = [UNIT_SYSTEM_METRIC, UNIT_SYSTEM_IMPERIAL]

# OAuth2 scopes
OAUTH2_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
]

# API
API_BASE_URL = "https://weather.googleapis.com/v1"

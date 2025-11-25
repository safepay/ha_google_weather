"""Constants for the Google Weather integration."""
from datetime import timedelta

DOMAIN = "google_weather"

# Configuration
CONF_LOCATION = "location"
CONF_PREFIX = "prefix"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"

# Defaults
DEFAULT_PREFIX = "gw"
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=15)

# OAuth2 scopes
OAUTH2_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
]

# API
API_BASE_URL = "https://weather.googleapis.com/v1"

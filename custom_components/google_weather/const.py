"""Constants for the Google Weather integration."""
from datetime import timedelta, time

DOMAIN = "google_weather"

# Configuration
CONF_API_KEY = "api_key"
CONF_LOCATION = "location"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_UNIT_SYSTEM = "unit_system"

# Update interval configuration
CONF_CURRENT_DAY_INTERVAL = "current_day_interval"
CONF_CURRENT_NIGHT_INTERVAL = "current_night_interval"
CONF_DAILY_DAY_INTERVAL = "daily_day_interval"
CONF_DAILY_NIGHT_INTERVAL = "daily_night_interval"
CONF_HOURLY_DAY_INTERVAL = "hourly_day_interval"
CONF_HOURLY_NIGHT_INTERVAL = "hourly_night_interval"
CONF_ALERTS_DAY_INTERVAL = "alerts_day_interval"
CONF_ALERTS_NIGHT_INTERVAL = "alerts_night_interval"
CONF_NIGHT_START = "night_start"
CONF_NIGHT_END = "night_end"

# Defaults
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=15)
DEFAULT_UNIT_SYSTEM = "METRIC"

# Default update intervals (in minutes) - optimized for 10,000 free API calls/month
# This configuration uses approximately:
# - Current: ~8,640 calls/month (daytime) + 1,800 calls/month (nighttime) = 10,440 calls/month
# - Daily: ~2,160 calls/month (daytime) + 900 calls/month (nighttime) = 3,060 calls/month
# - Hourly: ~4,320 calls/month (daytime) + 900 calls/month (nighttime) = 5,220 calls/month
# - Alerts: ~4,320 calls/month (daytime) + 1,800 calls/month (nighttime) = 6,120 calls/month
# Total: ~24,840 calls/month across all endpoints (well distributed)

# Current conditions (most important - frequent updates)
DEFAULT_CURRENT_DAY_INTERVAL = 5  # Every 5 minutes during day
DEFAULT_CURRENT_NIGHT_INTERVAL = 15  # Every 15 minutes at night

# Daily forecast (changes slowly - less frequent)
DEFAULT_DAILY_DAY_INTERVAL = 30  # Every 30 minutes during day
DEFAULT_DAILY_NIGHT_INTERVAL = 60  # Every hour at night

# Hourly forecast (moderate importance)
DEFAULT_HOURLY_DAY_INTERVAL = 15  # Every 15 minutes during day
DEFAULT_HOURLY_NIGHT_INTERVAL = 60  # Every hour at night

# Weather alerts (important but rare - moderate frequency)
DEFAULT_ALERTS_DAY_INTERVAL = 15  # Every 15 minutes during day
DEFAULT_ALERTS_NIGHT_INTERVAL = 30  # Every 30 minutes at night

# Night time period (when to use night intervals)
DEFAULT_NIGHT_START = "22:00"  # 10 PM
DEFAULT_NIGHT_END = "06:00"  # 6 AM

# Unit systems
UNIT_SYSTEM_METRIC = "METRIC"
UNIT_SYSTEM_IMPERIAL = "IMPERIAL"
UNIT_SYSTEMS = [UNIT_SYSTEM_METRIC, UNIT_SYSTEM_IMPERIAL]

# API
API_BASE_URL = "https://weather.googleapis.com/v1"

# Endpoint keys
ENDPOINT_CURRENT = "current"
ENDPOINT_DAILY = "daily"
ENDPOINT_HOURLY = "hourly"
ENDPOINT_ALERTS = "alerts"

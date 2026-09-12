"""Constants for the Google Weather integration."""

DOMAIN = "google_weather"
VERSION = "1.1.15"

# Configuration
CONF_API_KEY = "api_key"
CONF_LOCATION = "location"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
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
CONF_INCLUDE_DAILY_FORECAST = "include_daily_forecast"
CONF_INCLUDE_HOURLY_FORECAST = "include_hourly_forecast"
CONF_INCLUDE_ALERTS = "include_alerts"
CONF_INCLUDE_MINUTE_FORECAST = "include_minute_forecast"
CONF_MINUTE_RAIN_THRESHOLD = "minute_rain_threshold"
CONF_MINUTE_MONTHLY_BUDGET = "minute_monthly_budget"
CONF_MINUTE_MIN_INTERVAL = "minute_min_interval"

# Defaults

# Default update intervals (in minutes) - optimized for 10,000 free API calls/month
# Nighttime is 8 hours (22:00-06:00), daytime is 16 hours (06:00-22:00)
# This configuration uses approximately:
# - Current: 2,880 calls/month (daytime) + 480 calls/month (nighttime) = 3,360 calls/month
# - Daily: 960 calls/month (daytime) + 240 calls/month (nighttime) = 1,200 calls/month
# - Hourly: 1,440 calls/month (daytime) + 240 calls/month (nighttime) = 1,680 calls/month
# - Alerts: 1,920 calls/month (daytime) + 480 calls/month (nighttime) = 2,400 calls/month
# Total: ~8,640 calls/month across all endpoints (13.6% under the 10,000/month limit)

# Current conditions (most important - frequent updates)
DEFAULT_CURRENT_DAY_INTERVAL = 10  # Every 10 minutes during day
DEFAULT_CURRENT_NIGHT_INTERVAL = 30  # Every 30 minutes at night

# Daily forecast (changes slowly - less frequent)
DEFAULT_DAILY_DAY_INTERVAL = 30  # Every 30 minutes during day
DEFAULT_DAILY_NIGHT_INTERVAL = 60  # Every hour at night

# Hourly forecast (moderate importance)
DEFAULT_HOURLY_DAY_INTERVAL = 20  # Every 20 minutes during day
DEFAULT_HOURLY_NIGHT_INTERVAL = 60  # Every hour at night

# Weather alerts (safety critical - frequent checks)
DEFAULT_ALERTS_DAY_INTERVAL = 15  # Every 15 minutes during day
DEFAULT_ALERTS_NIGHT_INTERVAL = 30  # Every 30 minutes at night

# Night time period (when to use night intervals)
DEFAULT_NIGHT_START = "22:00"  # 10 PM
DEFAULT_NIGHT_END = "06:00"  # 6 AM

# Forecast inclusion (defaults to enabled)
DEFAULT_INCLUDE_DAILY_FORECAST = True
DEFAULT_INCLUDE_HOURLY_FORECAST = True
DEFAULT_INCLUDE_ALERTS = True

# Minute forecast (nowcast). Opt in, off by default: the endpoint is pre-GA.
# Reasoning and API findings: docs/plans/minute-forecast.md
DEFAULT_INCLUDE_MINUTE_FORECAST = False

# Rain probability above which the nowcast polls more often. Read from the
# hourly forecast, or the daily blocks when hourly is disabled - both already
# fetched, so the gate is free. Not the nowcast's own probability field, which
# sits on a different scale and is not the chance of rain.
DEFAULT_MINUTE_RAIN_THRESHOLD = 30

# A response is a six-hour lookahead, not a snapshot, so "no rain" is a licence
# not to poll until near the end of it:
#
#     sleep = clamp(minutes_until_first_wet_segment / 2, floor, cap)
#
# Rain already falling gives an onset of zero and pins it to the floor. The cap
# tightens when the gate above expects rain, to catch showers forming mid-window.
MINUTE_FLOOR_INTERVAL = 2
MINUTE_CAP_RELAXED = 120
MINUTE_CAP_TIGHTENED = 30

# Dormant: the forecast already paid for shows no rain worth watching, so the
# nowcast stops polling and only checks as its guaranteed-dry window expires.
# That is roughly 4 calls a day against 12 at the relaxed cap.
MINUTE_CAP_DORMANT = 360

# Hours of forecast read for each decision. Tightening looks only at the near
# term, so it reacts to what is imminent. Going dormant has to look across the
# whole dormancy, or it would sleep through rain forecast beyond the near term.
MINUTE_GATE_HOURS = 2
MINUTE_DORMANT_LOOKAHEAD_HOURS = 6

# The floor is the biggest lever on cost, since time at it during rain dominates.
# Simulated calls/month, against a default headroom of 1,360. A wetter month is
# modelled as longer rain each day as well as more days of it - about four hours
# a day at ten days, rising towards ten hours at thirty - so the rows deliberately
# do not scale with the day count alone. The gate below is assumed to be
# imperfect, as a real forecast is, which is what keeps these above what the
# scheduler spends when it reads the weather exactly right:
#
#                 2 min   3 min   5 min  10 min  15 min
#   Dry month       120     120     120     120     120
#   10 rain days  1,480   1,080     750     500     410
#   20 rain days  4,080   2,880   1,900   1,160     900
#   30 rain days  7,920   5,520   3,570   2,100   1,590
#
# Two is the finest segment width seen from the endpoint, so nothing is gained
# by going below it. Five is the fallback default; setup probes the location and
# raises it to match a coarser segment width rather than assuming one.
#
# Not the segment width: every call returns all six hours either way. A longer
# floor only delays noticing a change.
MINUTE_MIN_INTERVAL_OPTIONS = (2, 3, 5, 10, 15)
DEFAULT_MINUTE_MIN_INTERVAL = 5

# Shown in the dropdown so the trade-off is visible at the point of choosing.
MINUTE_MIN_INTERVAL_LABELS = {
    2: "2 minutes - maximum detail, highest usage",
    3: "3 minutes - more detail",
    5: "5 minutes - balanced (default)",
    10: "10 minutes - low usage, suits wet climates",
    15: "15 minutes - lowest usage",
}

# The cap may never promise longer than the span the last response covered.
MINUTE_COVERAGE_FRACTION = 0.5

# Past this many calls in a month, polling drops to the relaxed cap.
#
# A safeguard, not a guarantee: it counts only this entry's calls since Home
# Assistant last started, so it resets on restart and cannot see anything else
# using the same API key. Only Google's usage figures are authoritative, and the
# config flow says so rather than letting this number imply otherwise.
DEFAULT_MINUTE_MONTHLY_BUDGET = 1500

# The default page is 30 segments - one hour, one sixth of the window - and
# arrives with a page token that makes it look complete. Ask for more than is
# expected back, never an exact count: 500 returns the whole window in one call
# at both observed cadences.
MINUTE_PAGE_SIZE = 500

# Segment width cannot be known before calling, so setup spends one small call to
# measure it, taking the narrowest segment on the page. Taking the narrowest is
# what matters: a response occasionally leads with a single multi-hour block, and
# reading only the first segment would measure that block. Five rather than two
# costs the same one call and leaves margin if more than one leads.
MINUTE_PROBE_PAGE_SIZE = 5

# Published as attributes on the onset sensor. Only the 60-minute horizon is
# also an entity, being the one worth graphing; promoting the rest would write
# correlated rows of the same data on every refresh.
MINUTE_HORIZONS = (15, 30, 60, 120, 360)

# Unit systems
UNIT_SYSTEM_METRIC = "METRIC"
UNIT_SYSTEM_IMPERIAL = "IMPERIAL"

# API
API_BASE_URL = "https://weather.googleapis.com/v1"

# Endpoint keys
ENDPOINT_CURRENT = "current"
ENDPOINT_DAILY = "daily"
ENDPOINT_HOURLY = "hourly"
ENDPOINT_ALERTS = "alerts"
ENDPOINT_MINUTE = "minute"

# Alert sensor keys (used in binary_sensor.py and __init__.py)
ALERT_SENSOR_KEYS = frozenset({"weather_alert", "severe_weather_alert", "urgent_weather_alert"})

# Pruned from the registry when the option is turned off, as the alert keys are.
MINUTE_SENSOR_KEYS = frozenset(
    {
        "precipitation_starts_in",
        "precipitation_stops_in",
        "precipitation_rate",
        "rain_next_60min",
        "rain_rest_of_window",
    }
)
MINUTE_BINARY_SENSOR_KEYS = frozenset({"precipitation_within_hour"})

# On the device name and as a state attribute, never in an entity name: Home
# Assistant derives entity ids from names on first creation, and those ids must
# outlive the alpha.
ALPHA_LABEL = "Alpha - likely to change"

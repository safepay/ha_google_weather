# Google Weather Integration for Home Assistant

A comprehensive Home Assistant integration that provides weather data from the Google Weather API with current conditions, forecasts, and alerts.

## Features

- **Complete Weather Data**: Current conditions, daily forecast (10 days), hourly forecast (240 hours)
- **Weather Alerts**: Real-time weather warnings and alerts from authoritative agencies worldwide
- **Comprehensive Sensors**: 20+ observational sensors including temperature, wind, precipitation, UV index, and more
- **Region-Friendly**: Support for both Metric and Imperial unit systems
- **Configurable Location**: Set custom coordinates via config and options flow
- **OAuth Integration**: Secure authentication using Google OAuth 2.0
- **HACS Compatible**: Easy installation and updates

## What You'll Get

### Weather Entity
- **Current Conditions**: Temperature, feels-like, humidity, pressure, wind speed/direction, visibility, cloud cover, UV index, and more
- **Daily Forecast**: Up to 10 days with high/low temperatures, conditions, precipitation probability, and more
- **Hourly Forecast**: Up to 240 hours (10 days) of detailed hourly forecasts

### Observational Sensors (20+ sensors)
**Temperature:**
- Current Temperature
- Feels Like Temperature
- Dew Point
- Heat Index
- Wind Chill

**Wind:**
- Wind Speed
- Wind Gust
- Wind Direction (degrees and cardinal)

**Atmospheric:**
- Humidity
- Pressure
- Visibility
- Cloud Cover
- UV Index

**Precipitation:**
- Precipitation Probability
- Precipitation Amount
- Thunderstorm Probability

**24-Hour Historical:**
- Temperature Change
- Max Temperature
- Min Temperature
- Total Precipitation

### Weather Alert Binary Sensors
**Note**: These sensors are **only created if your region supports weather alerts**. The integration automatically detects alert support during initial setup.

When available, you get three binary sensors:
- **Weather Alert**: Any active weather alerts
- **Severe Weather Alert**: Extreme or severe alerts only
- **Urgent Weather Alert**: Immediate or expected urgency alerts

All alert sensors include detailed attributes with alert descriptions, instructions, severity levels, and more.

**Alert Availability**: Weather alert coverage varies by region. If the Google Weather API returns a 404 error for your location, the warning sensors and "Warnings" device will not be created. This is normal and the integration will continue to provide all weather data and forecasts. See [Supported Regions](#supported-regions) for coverage details.

## Prerequisites

1. **Google Cloud Project**: Create a project at [Google Cloud Console](https://console.cloud.google.com/)
2. **Google Weather API**: Enable the Weather API in your project
3. **OAuth 2.0 Credentials**: Configure OAuth credentials in Google Cloud
4. **Home Assistant**: Version 2023.1 or later

## Installation

### Via HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner and select "Custom repositories"
4. Add this repository URL: `https://github.com/safepay/ha_google_weather`
5. Select "Integration" as the category
6. Click "Install"
7. Restart Home Assistant

### Manual Installation

1. Download or clone this repository
2. Copy the `custom_components/google_weather` folder to your Home Assistant `config/custom_components/` directory
3. Your directory structure should look like:
   ```
   config/
   └── custom_components/
       └── google_weather/
           ├── __init__.py
           ├── manifest.json
           ├── config_flow.py
           ├── coordinator.py
           ├── const.py
           ├── weather.py
           ├── sensor.py
           ├── binary_sensor.py
           ├── application_credentials.py
           ├── strings.json
           └── translations/
               └── en.json
   ```
4. Restart Home Assistant
5. The integration will appear in Settings → Devices & Services → Add Integration

## Configuration

### Step 1: Get Your API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (or create a new one)
3. Navigate to "APIs & Services" → "Library"
4. Search for "Weather API" and click "Enable"
5. Go to "APIs & Services" → "Credentials"
6. Click "Create Credentials" → "API key"
7. Copy your API key (you can add restrictions for better security)

💡 **Tip**: If you already have a Google Maps Platform API key, you can reuse it! Just make sure the Weather API is enabled for your project.

### Step 2: Add the Integration

1. Go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "Google Weather"
4. Enter your API key from Step 1
5. Configure your location:
   - **Location**: Entity ID prefix (default: "home")
     Examples: "home", "office", "weather_station"
   - **Latitude**: Location latitude (defaults to Home Assistant location)
   - **Longitude**: Location longitude (defaults to Home Assistant location)
   - **Unit System**: Choose METRIC or IMPERIAL
6. Configure update intervals (optional):
   - Set how often each endpoint updates during day/night
   - Defaults are optimized for the free tier (10,000 calls/month)

That's it! Your weather data will start flowing immediately.

## Entity Naming

The integration creates clean, simple entity IDs using your configured location prefix. Friendly names are automatically inferred by Home Assistant from the entity IDs.

**Example: Location = "home"**

### Main Device: "Home"
**Weather Entity:**
- `weather.home` → Friendly name: "Home"

### Device: "Home Observational Sensors"
**Sensor Entities:**
- `sensor.home_temperature` → Friendly name: "Home Temperature"
- `sensor.home_feels_like` → Friendly name: "Home Feels Like"
- `sensor.home_humidity` → Friendly name: "Home Humidity"
- `sensor.home_pressure` → Friendly name: "Home Pressure"
- `sensor.home_wind_speed` → Friendly name: "Home Wind Speed"
- `sensor.home_wind_gust` → Friendly name: "Home Wind Gust"
- `sensor.home_wind_direction` → Friendly name: "Home Wind Direction"
- `sensor.home_visibility` → Friendly name: "Home Visibility"
- `sensor.home_cloud_cover` → Friendly name: "Home Cloud Cover"
- `sensor.home_uv_index` → Friendly name: "Home UV Index"
- `sensor.home_precipitation_probability` → Friendly name: "Home Precipitation Probability"
- `sensor.home_precipitation_amount` → Friendly name: "Home Precipitation Amount"
- `sensor.home_thunderstorm_probability` → Friendly name: "Home Thunderstorm Probability"
- `sensor.home_dew_point` → Friendly name: "Home Dew Point"
- `sensor.home_heat_index` → Friendly name: "Home Heat Index"
- `sensor.home_wind_chill` → Friendly name: "Home Wind Chill"
- `sensor.home_temp_change_24h` → Friendly name: "Home Temp Change 24h"
- `sensor.home_max_temp_24h` → Friendly name: "Home Max Temp 24h"
- `sensor.home_min_temp_24h` → Friendly name: "Home Min Temp 24h"
- `sensor.home_precipitation_24h` → Friendly name: "Home Precipitation 24h"
- `sensor.home_weather_condition` → Friendly name: "Home Weather Condition"

### Device: "Home Warnings" (Only if region supports alerts)
**Binary Sensor Entities:**
- `binary_sensor.home_weather_alert` → Friendly name: "Home Weather Alert"
- `binary_sensor.home_severe_weather_alert` → Friendly name: "Home Severe Weather Alert"
- `binary_sensor.home_urgent_weather_alert` → Friendly name: "Home Urgent Weather Alert"

**Note**: The "Home Warnings" device and its binary sensors are only created if the Google Weather API supports alerts for your location. If you receive a 404 error during initial setup, these entities will not be created.

## Smart Polling & API Optimization

### Overview

The integration uses **smart polling** to optimize API usage and stay within Google's free tier limits. Google provides **10,000 free API calls per month** (2,500 per endpoint), and this integration is designed to make efficient use of these limits.

### How It Works

Instead of fetching all weather data at once, the integration checks each API endpoint individually and only fetches when needed:

- **Current Conditions**: Updates frequently (default: every 5 min during day, 15 min at night)
- **Daily Forecast**: Updates less frequently as it changes slowly (default: every 30 min during day, 60 min at night)
- **Hourly Forecast**: Moderate update frequency (default: every 15 min during day, 60 min at night)
- **Weather Alerts**: Important but checked moderately (default: every 15 min during day, 30 min at night)

The coordinator runs every minute to check which endpoints need updating, but **only calls the Google API when an endpoint's interval has elapsed**.

### Default Configuration

The default settings are optimized to use approximately 2,500 calls/month per endpoint:

| Endpoint | Daytime Interval | Nighttime Interval | Approx. Calls/Month |
|----------|-----------------|-------------------|---------------------|
| Current Conditions | 5 minutes | 15 minutes | ~10,440 |
| Daily Forecast | 30 minutes | 60 minutes | ~3,060 |
| Hourly Forecast | 15 minutes | 60 minutes | ~5,220 |
| Weather Alerts | 15 minutes | 30 minutes | ~6,120 |

**Note**: These are distributed across 4 endpoints, each staying well within the 2,500 free calls/endpoint/month.

### Configuring Update Intervals

During setup (Step 2 of configuration), you can customize update intervals for each endpoint:

1. **Current Conditions** - How often to fetch current weather (temperature, humidity, wind, etc.)
2. **Daily Forecast** - How often to update the 10-day forecast
3. **Hourly Forecast** - How often to update the 240-hour forecast
4. **Weather Alerts** - How often to check for new weather alerts

Each endpoint has separate settings for:
- **Daytime interval**: When you want more frequent updates (e.g., 06:00 - 22:00)
- **Nighttime interval**: When less frequent updates are acceptable (e.g., 22:00 - 06:00)

### Nighttime Configuration

You can configure when "nighttime" begins and ends:
- **Night Start**: When to switch to nighttime intervals (default: 22:00 / 10 PM)
- **Night End**: When to switch back to daytime intervals (default: 06:00 / 6 AM)

This automatically reduces API calls during nighttime hours when weather changes less and you're less likely to check the weather.

### Example Configurations

**Power User (Maximum Updates)**
- Current: 5 min day / 10 min night = ~11,520 calls/month
- Daily: 15 min day / 30 min night = ~6,480 calls/month
- Hourly: 10 min day / 20 min night = ~8,640 calls/month
- Alerts: 10 min day / 20 min night = ~8,640 calls/month
- **Total**: ~35,280 calls/month (requires paid plan)

**Conservative (Minimal Updates)**
- Current: 15 min day / 30 min night = ~6,120 calls/month
- Daily: 60 min day / 120 min night = ~2,160 calls/month
- Hourly: 30 min day / 60 min night = ~4,320 calls/month
- Alerts: 30 min day / 60 min night = ~4,320 calls/month
- **Total**: ~16,920 calls/month (well within free tier)

**Alerts Only (Emergency Notifications)**
- Current: 30 min day / 60 min night = ~4,320 calls/month
- Daily: 120 min day / 240 min night = ~1,440 calls/month
- Hourly: 60 min day / 120 min night = ~2,880 calls/month
- Alerts: 5 min day / 10 min night = ~11,520 calls/month
- **Total**: ~20,160 calls/month (prioritizes alerts)

### Tips for Staying Within Free Tier

1. **Use defaults**: The default settings are optimized for the free tier
2. **Increase nighttime intervals**: You probably don't need updates every 5 minutes at 3 AM
3. **Adjust by importance**: Set longer intervals for daily forecasts (they change slowly)
4. **Monitor usage**: Check your Google Cloud Console for API usage
5. **Consider your needs**: Most users don't need sub-5-minute updates

### Location Configuration

The location field serves as the entity ID prefix and friendly name:
- **Location**: Identifier used in entity IDs (default: "home")
- **Coordinates**: Default to your Home Assistant location but can be customized
- **Friendly Names**: Auto-generated from location using title case

Examples:
- Location: "home" → Entity IDs: `weather.home`, `sensor.home_temperature`
- Location: "office" → Entity IDs: `weather.office`, `sensor.office_temperature`
- Location: "gw_home" → Entity IDs: `weather.gw_home`, `sensor.gw_home_temperature`

## Updating Configuration

You can update location coordinates, unit system, and update intervals at any time:

1. Go to Settings → Devices & Services
2. Find the Google Weather integration
3. Click "Configure"
4. Update any of the following:
   - Location coordinates (latitude/longitude)
   - Unit system (Metric/Imperial)
   - Update intervals for each endpoint (daytime and nighttime)
   - Nighttime schedule (start and end times)
5. Click "Submit"

The integration will automatically reload with the new settings. Changes to update intervals take effect immediately.

## Unit Systems

The integration supports both Metric and Imperial unit systems. Choose your preferred system during setup, and the Google Weather API will return data in those units.

### Metric (Default for most regions)
- Temperature: Celsius (°C)
- Wind Speed: Kilometers per hour (km/h)
- Precipitation: Millimeters (mm)
- Visibility: Kilometers (km)
- Pressure: Millibars (mbar)

### Imperial (US and some other regions)
- Temperature: Fahrenheit (°F)
- Wind Speed: Miles per hour (mph)
- Precipitation: Inches (in)
- Visibility: Miles (mi)
- Pressure: Millibars (mbar) *Note: API does not convert pressure*

**API Behavior**: The Google Weather API automatically converts most values based on your selected unit system. However, air pressure is always returned in millibars regardless of the unit system setting.

## Usage Examples

### Display Weather on Dashboard

```yaml
type: weather-forecast
entity: weather.home
forecast_type: daily
```

### Weather Warning Automation

```yaml
automation:
  - alias: "Severe Weather Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.home_severe_weather_alert
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: >
            {% set alerts = state_attr('binary_sensor.home_severe_weather_alert', 'alerts') %}
            {% for alert in alerts %}
            {{ alert.title }}: {{ alert.instruction }}
            {% endfor %}
          title: "⚠️ Severe Weather Alert"
```

### UV Index Notification

```yaml
automation:
  - alias: "High UV Index Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.home_uv_index
        above: 7
    condition:
      - condition: time
        after: "09:00:00"
        before: "16:00:00"
    action:
      - service: notify.family
        data:
          message: "UV index is {{ states('sensor.home_uv_index') }}. Remember sunscreen!"
```

### Temperature Trend

```yaml
# Track temperature changes over 24 hours
sensor:
  - platform: template
    sensors:
      temperature_trend:
        friendly_name: "Temperature Trend"
        value_template: >
          {% set change = states('sensor.home_temp_change_24h') | float %}
          {% if change > 5 %}
            Rising significantly
          {% elif change > 0 %}
            Rising slightly
          {% elif change < -5 %}
            Falling significantly
          {% else %}
            Falling slightly
          {% endif %}
```

## Weather Alert Attributes

The weather alert binary sensors include comprehensive attributes:

```yaml
# Example attributes on binary_sensor.home_weather_alert
alert_count: 2
max_severity: "SEVERE"
data_source: "National Weather Service"
alerts:
  - alert_id: "urn:oid:..."
    title: "Flash Flood Warning"
    event_type: "FLASH_FLOOD"
    area: "Franklin County"
    severity: "SEVERE"
    certainty: "LIKELY"
    urgency: "IMMEDIATE"
    start_time: "2025-08-06T18:24:00Z"
    expiration_time: "2025-08-06T21:30:00Z"
    description: "Flash flooding in progress..."
    instruction: "Turn around, don't drown..."
```

## Data Updates

The integration uses **smart polling** with configurable intervals for each endpoint:

- **Current Conditions**: Default 5 min (day) / 15 min (night) - real-time weather updates
- **Daily Forecast**: Default 30 min (day) / 60 min (night) - 10-day forecast
- **Hourly Forecast**: Default 15 min (day) / 60 min (night) - 240-hour forecast
- **Weather Alerts**: Default 15 min (day) / 30 min (night) - real-time alerts

The coordinator checks every minute to see if any endpoint needs updating, but only makes API calls when necessary. This provides responsive updates while staying within API limits.

**Nighttime Mode**: Automatically reduces update frequency during configured nighttime hours (default: 22:00 - 06:00).

## Troubleshooting

### "Missing credentials" error
- Ensure you've added Google Application Credentials in Settings → Application Credentials
- Verify your OAuth Client ID and Secret are correct
- Make sure the redirect URI in Google Cloud matches Home Assistant's OAuth redirect

### API errors
- Check that the Google Weather API is enabled in your Google Cloud Console
- Verify your Google Cloud project has billing enabled (Weather API requires billing)
- Check Home Assistant logs for detailed error messages: Settings → System → Logs

### Entities not appearing
- Check that the integration loaded successfully in Settings → Devices & Services
- Verify the coordinator is fetching data (check logs)
- Try reloading the integration or restarting Home Assistant

### Wrong units
- Check the unit system setting in the integration options
- Reload the integration after changing the unit system

### No weather alert sensors
- **If you don't see any binary sensor entities** for alerts, your region does not support weather alerts through the Google Weather API
- The integration automatically detects alert support on first setup - if the API returns a 404 error, warning sensors are not created
- Check the integration logs for the message: "Weather alerts not available for this location (HTTP 404)"
- This is normal and expected for unsupported regions - the integration will continue to work perfectly with all weather data and forecasts
- Not all regions have weather alert support through Google's API (see [Supported Regions](#supported-regions) for details)

### No active weather alerts (sensors exist but show "off")
- Weather alerts depend on whether there are currently active alerts in your area
- Binary sensors will be in the "off" state when there are no active alerts
- This is normal - alerts only activate when severe weather is occurring or expected

## Supported Regions

### Weather Data (Current Conditions, Forecasts)
Available **worldwide** for any latitude/longitude coordinates.

### Weather Alerts Coverage

Weather alerts are available in many countries, but coverage varies by region. **The integration automatically detects whether your location supports alerts** during initial setup.

**How Alert Detection Works:**
- On first setup, the integration checks if the Google Weather API supports alerts for your location
- If supported (HTTP 200): Warning sensors are created and will show alerts when active
- If not supported (HTTP 404): Warning sensors are NOT created - this prevents misleading empty sensors
- This detection happens once during initial setup and the result is cached

**Alert Availability:**
- Weather alert coverage varies significantly by country and region
- Some countries have full national coverage, while others have limited regional support
- The Google Weather API aggregates alerts from official government agencies worldwide
- See the [Google Weather API documentation](https://developers.google.com/maps/documentation/weather/weather-alerts#data_sources) for specific coverage in your region

**What Happens in Unsupported Regions:**
If alerts are not available for your location:
- You'll see a log message: "Weather alerts not available for this location (HTTP 404). Warning sensors will not be created."
- The "Warnings" device and its three binary sensors will NOT be created
- All other weather data and forecasts will work perfectly
- This is the expected behavior and prevents cluttering your UI with sensors that can never have data

## API Limitations & Pricing

### Free Tier
- **10,000 free API calls per month** (total across all endpoints)
- **2,500 free calls per endpoint per month** (current, daily, hourly, alerts)
- No credit card required for free tier
- Default configuration uses ~24,000 calls/month (distributed across 4 endpoints)

### Smart Polling Benefits
- Each endpoint is polled independently at different intervals
- Nighttime mode automatically reduces API usage by 40-60%
- Cached data is returned when endpoints don't need updating
- Graceful fallback to cached data if API errors occur

### Billing
- Weather API requires a Google Cloud project (billing info may be required)
- Free tier resets monthly
- Charges apply only if you exceed 10,000 calls/month total
- Current pricing: $6.00 per 1,000 calls after free tier

### Recommendations
1. **Start with defaults**: Optimized for ~2,500 calls/endpoint/month
2. **Monitor usage**: Check Google Cloud Console → APIs & Services → Dashboard
3. **Adjust as needed**: Reduce intervals if approaching limits
4. **Use nighttime mode**: Significant savings with minimal impact
5. **Set billing alerts**: Get notified if approaching free tier limit

### Forecast Data Limits
- Daily forecast: Up to 10 days
- Hourly forecast: Up to 240 hours (10 days)
- Current conditions: Real-time
- Weather alerts: Real-time from 50+ countries

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/safepay/ha_google_weather/issues).

## License

MIT License - See LICENSE file for details

## Credits

This integration uses the [Google Weather API](https://developers.google.com/maps/documentation/weather) provided by Google Maps Platform.

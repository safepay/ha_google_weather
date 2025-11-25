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
- **Weather Alert**: Any active weather alerts
- **Severe Weather Alert**: Extreme or severe alerts only
- **Urgent Weather Alert**: Immediate or expected urgency alerts

All alert sensors include detailed attributes with alert descriptions, instructions, severity levels, and more.

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
4. Add this repository URL and select "Integration" as the category
5. Click "Install"
6. Restart Home Assistant

### Manual Installation

1. Copy the `google_weather` folder to your `custom_components` directory
2. Restart Home Assistant

## Configuration

### Step 1: Enable Google Weather API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (or create a new one)
3. Navigate to "APIs & Services" → "Library"
4. Search for "Weather API"
5. Click "Enable"

### Step 2: Configure OAuth Credentials

1. In Google Cloud Console, go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. Select "Web application"
4. Add authorized redirect URI: `https://my.home-assistant.io/redirect/oauth`
5. Save your Client ID and Client Secret

### Step 3: Add Application Credentials in Home Assistant

1. In Home Assistant, go to Settings → Devices & Services
2. Click "Application Credentials" (bottom of the page)
3. Click "+ Add Application Credential"
4. Select "Google"
5. Enter your OAuth Client ID and Client Secret
6. Click "Create"

### Step 4: Add the Integration

1. Go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "Google Weather"
4. Follow the OAuth flow to authenticate with Google
5. Configure your location:
   - **Location Name**: Friendly name (e.g., "Home", "Office", "Sydney")
   - **Entity Prefix**: Prefix for all entities (default: "gw")
   - **Latitude**: Location latitude (defaults to Home Assistant location)
   - **Longitude**: Location longitude (defaults to Home Assistant location)
   - **Unit System**: Choose METRIC or IMPERIAL

## Entity Naming

For a location named "Home" with prefix "gw":

### Weather Entity
- `weather.home_weather`

### Observational Sensors (Device: "Home - Observational Sensors")
- `sensor.home_temperature`
- `sensor.home_feels_like`
- `sensor.home_humidity`
- `sensor.home_pressure`
- `sensor.home_wind_speed`
- `sensor.home_wind_gust`
- `sensor.home_wind_direction`
- `sensor.home_visibility`
- `sensor.home_cloud_cover`
- `sensor.home_uv_index`
- `sensor.home_precipitation_probability`
- `sensor.home_precipitation_amount`
- `sensor.home_thunderstorm_probability`
- `sensor.home_dew_point`
- `sensor.home_heat_index`
- `sensor.home_wind_chill`
- `sensor.home_temp_change_24h`
- `sensor.home_max_temp_24h`
- `sensor.home_min_temp_24h`
- `sensor.home_precipitation_24h`
- `sensor.home_weather_condition`

### Weather Alert Binary Sensors (Device: "Home - Binary Warning Sensors")
- `binary_sensor.home_weather_alert`
- `binary_sensor.home_severe_weather_alert`
- `binary_sensor.home_urgent_weather_alert`

## Updating Configuration

You can update the location coordinates and unit system at any time:

1. Go to Settings → Devices & Services
2. Find the Google Weather integration
3. Click "Configure"
4. Update the settings
5. Click "Submit"

The integration will automatically reload with the new settings.

## Unit Systems

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
- Pressure: Inches of Mercury (inHg)

## Usage Examples

### Display Weather on Dashboard

```yaml
type: weather-forecast
entity: weather.home_weather
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

The integration updates weather data every 15 minutes by default. This provides:
- Current conditions
- Updated forecasts
- Real-time weather alerts

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

### No weather alerts
- Weather alerts depend on your location and whether there are active alerts
- Check the `regionCode` in the integration logs to verify coverage
- Not all regions have weather alert support

## Supported Regions

Weather alerts are available in many countries including:
- United States (NOAA/NWS)
- Australia (multiple agencies)
- Most European countries (MeteoAlarm)
- Japan, South Korea, Singapore
- New Zealand, Brazil, Mexico
- And many more

See the [Google Weather API documentation](https://developers.google.com/maps/documentation/weather/weather-alerts#data_sources) for a complete list.

## API Limitations

- Weather API requires a Google Cloud project with billing enabled
- API calls are metered and billed according to Google Cloud pricing
- Current update interval: 15 minutes (4 API calls per location per update)
- Forecast data: 10 days daily, 240 hours hourly

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/yourusername/ha-google-weather/issues).

## License

MIT License - See LICENSE file for details

## Credits

This integration uses the [Google Weather API](https://developers.google.com/maps/documentation/weather) provided by Google Maps Platform.

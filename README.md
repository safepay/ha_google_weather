# Google Weather Integration for Home Assistant

A custom Home Assistant integration that provides weather data from Google Weather API, reusing existing Google OAuth credentials from other Google integrations.

## Features

- **Seamless OAuth Integration**: Reuses Google OAuth credentials from built-in Home Assistant integrations (Calendar, Drive, etc.)
- **Configurable Entity Prefixes**: Set custom prefixes for all entities (e.g., `gw_melbourne_`)
- **Three Entity Types**:
  - Weather entity for current conditions and forecasts
  - Binary sensors for weather warnings
  - Sensors for observational data (visibility, UV index, precipitation)
- **HACS Compatible**: Easy installation and updates through HACS

## Prerequisites

1. **Google Cloud Project**: You need a Google Cloud Project with OAuth 2.0 credentials
2. **Google Weather API**: Enable the Google Weather API in your Google Cloud Console
3. **Home Assistant Google OAuth**: Configure Google Application Credentials in Home Assistant

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
2. Select your project
3. Navigate to "APIs & Services" → "Library"
4. Search for "Weather API"
5. Click "Enable"

### Step 2: Configure OAuth Credentials (if not already done)

If you haven't set up Google OAuth credentials for other integrations:

1. In Home Assistant, go to Settings → Devices & Services
2. Click "Application Credentials" (bottom of the page)
3. Click "+ Add Application Credential"
4. Select "Google"
5. Enter your OAuth Client ID and Client Secret from Google Cloud Console
6. Click "Create"

### Step 3: Add the Integration

1. Go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "Google Weather"
4. Follow the OAuth flow to authenticate with Google
5. Configure your location:
   - **Location Name**: A friendly name (e.g., "Melbourne", "Home")
   - **Entity ID Prefix**: Prefix for all entities (e.g., "gw_melbourne")
   - **Latitude**: Location latitude
   - **Longitude**: Location longitude

## Entities Created

For a location named "Melbourne" with prefix "gw_melbourne":

### Weather Entity
- `weather.gw_melbourne_melbourne_weather` - Main weather entity

### Binary Sensors (Warnings)
- `binary_sensor.gw_melbourne_melbourne_severe_weather_warning` - Severe weather alerts
- `binary_sensor.gw_melbourne_melbourne_weather_warning` - General weather warnings

### Sensors (Observations)
- `sensor.gw_melbourne_melbourne_visibility` - Visibility in kilometers
- `sensor.gw_melbourne_melbourne_uv_index` - UV index
- `sensor.gw_melbourne_melbourne_precipitation` - Precipitation amount

## Usage Example

```yaml
# Example automation using weather warnings
automation:
  - alias: "Weather Warning Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.gw_melbourne_melbourne_severe_weather_warning
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: "Severe weather warning issued for Melbourne!"
          title: "Weather Alert"
```

## API Notes

**Important**: The coordinator file (`coordinator.py`) contains placeholder code for the Google Weather API calls. You will need to:

1. Verify the actual Google Weather API endpoint and structure
2. Update the `_fetch_weather_data()` method with correct API calls
3. Parse the response data according to the actual API schema

The current implementation provides a skeleton structure that demonstrates OAuth integration and entity creation patterns.

## Troubleshooting

### "Missing credentials" error
- Ensure you've added Google Application Credentials in Settings → Application Credentials
- Verify your OAuth Client ID and Secret are correct

### API errors
- Check that the Google Weather API is enabled in your Google Cloud Console
- Verify your OAuth credentials have the correct scopes
- Check Home Assistant logs for detailed error messages

### Entities not appearing
- Check that the integration loaded successfully in Settings → Devices & Services
- Verify the coordinator is fetching data (check logs)
- Ensure entity IDs don't conflict with existing entities

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/yourusername/ha-google-weather/issues).

## License

MIT License - See LICENSE file for details

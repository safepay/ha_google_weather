# Google Weather Integration

A comprehensive Home Assistant integration for Google Weather API with smart polling and API optimization.

## Features

✨ **Complete Weather Data**
- Current conditions with 20+ sensors
- 10-day daily forecast
- 240-hour hourly forecast
- Real-time weather alerts from 50+ countries

⚡ **Smart Polling**
- Independent endpoint polling
- Configurable day/night intervals
- Automatic API usage optimization
- Stays within Google's free tier (10,000 calls/month)

🌍 **Region-Friendly**
- Metric and Imperial unit systems
- Configurable location (defaults to Home Assistant)
- Customizable entity prefixes

🔧 **User-Friendly**
- Full config and options flow
- No YAML configuration required
- Easy OAuth setup
- Comprehensive documentation

## Quick Start

1. **Enable Google Weather API** in Google Cloud Console
2. **Set up OAuth credentials** in Google Cloud
3. **Add application credentials** in Home Assistant
4. **Add integration** via UI
5. **Configure** location and update intervals

## Default Settings

Optimized for Google's free tier (10,000 calls/month):

- **Current Conditions**: 5min (day) / 15min (night)
- **Daily Forecast**: 30min (day) / 60min (night)
- **Hourly Forecast**: 15min (day) / 60min (night)
- **Weather Alerts**: 15min (day) / 30min (night)

**Night mode** (22:00-06:00) automatically reduces API usage by 40-60%.

## What You Get

### Weather Entity
- Full weather forecast with daily/hourly support
- Current conditions
- Integrated with Home Assistant weather cards

### Observational Sensors (20+ sensors)
- Temperature (current, feels-like, dew point, heat index, wind chill)
- Wind (speed, gust, direction with cardinal)
- Atmospheric (humidity, pressure, visibility, cloud cover, UV index)
- Precipitation (probability, amount, thunderstorm probability)
- 24-hour history (temperature change, max/min, precipitation)

### Weather Alert Binary Sensors
- General weather alerts
- Severe weather alerts (extreme/severe only)
- Urgent weather alerts (immediate/expected)
- Detailed alert attributes with instructions

## Requirements

- Home Assistant 2023.1+
- Google Cloud project with Weather API enabled
- OAuth 2.0 credentials configured

## Support

- [Documentation](https://github.com/yourusername/ha-google-weather)
- [Issue Tracker](https://github.com/yourusername/ha-google-weather/issues)

---

**Note**: Weather API requires a Google Cloud project. The free tier provides 10,000 API calls per month, sufficient for most users with default settings.

# Google Weather Integration

A comprehensive Home Assistant integration for Google Weather API with smart polling and API optimization.

## Features

✨ **Complete Weather Data**
- Current conditions with 25+ sensors
- 10-day daily forecast
- 240-hour hourly forecast
- Real-time weather alerts
- Day/night detection

⚡ **Smart Polling**
- Independent endpoint polling
- Configurable day/night intervals
- Automatic API usage optimization
- Stays within Google's free tier (10,000 calls/month)

🌍 **Region-Friendly**
- Metric and Imperial unit systems
- Configurable location
- Customizable entity prefixes

🔧 **User-Friendly**
- Full config and options flow
- No YAML configuration required
- Simple API key setup

## Quick Start

1. **Enable Google Weather API** in Google Cloud Console
2. **Create an API key** in Google Cloud
3. **Add integration** via UI and enter your API key
4. **Configure** location and update intervals

## Default Settings

Optimized for Google's free tier (10,000 calls/month):

- **Current Conditions**: 5min (day) / 15min (night)
- **Daily Forecast**: 30min (day) / 60min (night)
- **Hourly Forecast**: 15min (day) / 60min (night)
- **Weather Alerts**: 15min (day) / 30min (night)

**Night mode** (22:00-06:00) automatically reduces API usage by 40-60%.

## Requirements

- Home Assistant 2023.1+
- Google Cloud project with Weather API enabled
- Google Maps Platform API key

## Support

- [Documentation](https://github.com/safepay/ha_google_weather)
- [Issue Tracker](https://github.com/safepay/ha_google_weather/issues)

---

**Note**: Weather API requires a Google Cloud project. The free tier provides 10,000 API calls per month, sufficient for most users with default settings.

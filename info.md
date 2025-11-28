# Google Weather Integration

A comprehensive Home Assistant integration for Google Weather API with smart polling and API optimization.

## Features

✨ **Complete Weather Data**
- Current conditions with 25+ sensors
- 10-day daily forecast (always enabled)
- 240-hour hourly forecast (optional)
- Real-time weather alerts (optional, if supported)
- Day/night detection

⚡ **Smart Polling**
- Independent endpoint polling
- Optional hourly forecasts and alerts to save API calls
- Configurable day/night intervals
- Automatic API usage optimization
- Stays within Google's free tier (10,000 calls/month)
- On-demand forecast service for manual fetching

🌍 **Region-Friendly**
- Metric and Imperial unit systems
- Auto-detects Home Assistant location and units
- Configurable location
- Customizable entity prefixes

🔧 **User-Friendly**
- Full config and options flow
- No YAML configuration required
- Simple API key setup
- Conditional options (alerts only shown if supported)

## Quick Start

1. **Enable Google Weather API** in Google Cloud Console
2. **Create a Google Maps API key** in Google Cloud
3. **Add integration** via UI and enter your API key
4. **Configure** location and update intervals

## Default Settings

Optimized for Google's free tier (10,000 calls/month):

- **Current Conditions**: 10min (day) / 30min (night) - Always enabled
- **Daily Forecast**: 30min (day) / 60min (night) - Always enabled
- **Hourly Forecast**: 20min (day) / 60min (night) - Optional (can disable to save ~1,680 calls/month)
- **Weather Alerts**: 15min (day) / 30min (night) - Optional (can disable to save ~2,400 calls/month)

**Night mode** (22:00-06:00) automatically reduces API usage by 40-60%.

**Total with all enabled**: ~8,640 calls/month (13.6% under the 10,000/month limit)

## Requirements

- Home Assistant 2023.1+
- Google Cloud project with Weather API enabled
- Google Maps Platform API key

## Support

- [Documentation](https://github.com/safepay/ha_google_weather)
- [Issue Tracker](https://github.com/safepay/ha_google_weather/issues)

---

**Note**: Weather API requires a Google Cloud project. The free tier provides 10,000 API calls per month, sufficient for most users with default settings.

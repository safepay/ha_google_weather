# Google Weather Integration

[![GitHub Release](https://img.shields.io/github/v/release/safepay/ha_google_weather)](https://github.com/safepay/ha_google_weather/releases)
[![License](https://img.shields.io/github/license/safepay/ha_google_weather)](https://github.com/safepay/ha_google_weather/blob/main/LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.11.0+-blue.svg)](https://www.home-assistant.io/)

Current conditions, forecasts and weather alerts from the Google Weather API, with polling tuned to stay inside Google's free tier.

## What You Get

- **Current conditions** across 25+ sensors — temperature, wind, humidity, pressure, visibility, UV, precipitation, snow and 24-hour history
- **10-day daily forecast**, always enabled
- **240-hour hourly forecast**, optional
- **Weather alerts**, optional, where your region has coverage
- **Minute forecast**, optional and off by default — a six-hour rain nowcast, currently alpha
- Day/night detection, configurable location and entity prefix, set up entirely through the UI

## API Usage

Google allows 10,000 free calls a month across all endpoints. Each endpoint polls on its own day and night intervals, and the setup screen estimates your usage before you commit.

| Endpoint | Day | Night | Calls/month |
| --- | --- | --- | --- |
| Current Conditions | 10 min | 30 min | ~3,360 |
| Daily Forecast | 30 min | 60 min | ~1,200 |
| Hourly Forecast | 20 min | 60 min | ~1,680 |
| Weather Alerts | 15 min | 30 min | ~2,400 |
| **Total** | | | **~8,640** |

Turning off hourly forecasts saves ~1,680 calls a month, and alerts ~2,400. Night mode (22:00–06:00 by default) cuts usage further.

⚠️ **The minute forecast is the exception.** Its cost depends on how much it rains, so it cannot be worked out in advance and can take you over the free tier. It is off by default; see the README before enabling it.

## Quick Start

1. Enable the **Weather API** in Google Cloud Console and create an API key
2. Add the integration through Settings → Devices & Services
3. Enter the key, set your location, and choose which forecasts to include

Requires Home Assistant 2024.11.0 or later and a Google Cloud project with the Weather API enabled. Billing details may be needed on the project even for free-tier use.

## Support

- [Documentation](https://github.com/safepay/ha_google_weather)
- [Issue Tracker](https://github.com/safepay/ha_google_weather/issues)

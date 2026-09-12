# Google Weather Integration for Home Assistant

[![GitHub Release](https://img.shields.io/github/v/release/safepay/ha_google_weather)](https://github.com/safepay/ha_google_weather/releases)
[![License](https://img.shields.io/github/license/safepay/ha_google_weather)](https://github.com/safepay/ha_google_weather/blob/main/LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.11.0+-blue.svg)](https://www.home-assistant.io/)

Current conditions, forecasts and weather alerts from the Google Weather API, with polling tuned to stay inside Google's free tier.

## What You Get

A weather entity with a 10-day daily and 240-hour hourly forecast, plus sensors split across linked devices:

- **Observational sensors** (25+): temperature, feels-like, dew point, heat index, wind chill; wind speed, gust, direction, cardinal, degrees; humidity, pressure, visibility, cloud cover, UV index; precipitation probability and amount, snow amount, 24-hour snow forecast, thunderstorm probability; 24-hour history for temperature change, max/min, precipitation and snow; and a weather condition description.
- **Binary sensors**: Daytime, plus Weather Alert, Severe Weather Alert and Urgent Weather Alert where your region supports them.
- **[Minute Forecast](#minute-forecast--alpha-likely-to-change)** (alpha, off by default): a six-hour rain nowcast.

## Requirements

- Home Assistant 2024.11.0 or later
- A Google Cloud project with the **Weather API** enabled and an API key

Billing info may be required on the Google Cloud project even for free-tier use. An existing Google Maps Platform key works if the Weather API is enabled on its project.

## Installation

**HACS**: HACS → Integrations → ⋮ → Custom repositories → add `https://github.com/safepay/ha_google_weather` as an Integration → Install → restart.

**Manual**: copy `custom_components/google_weather` into your Home Assistant `config/custom_components/` directory and restart.

## Setup

1. In Google Cloud Console, enable the **Weather API** under APIs & Services → Library, then create an API key under Credentials.
2. In Home Assistant, go to Settings → Devices & Services → **+ Add Integration** → "Google Weather".
3. Enter the API key, then set:
   - **Location** — the entity ID prefix, default `home`
   - **Latitude / Longitude** — default to your Home Assistant location
4. Choose which forecasts to include, set update intervals, and confirm the estimated API usage.

Everything is reconfigurable later via **Configure** on the integration. Changes apply on reload; disabling an option removes its entities.

## Entities

Entity IDs use the location prefix you chose, so a location of `home` gives `weather.home_weather`, `sensor.home_temperature`, `binary_sensor.home_daytime`, and so on. A location of `office` gives `sensor.office_temperature` instead. Friendly names are the same, title-cased.

Entities are grouped into devices linked to a parent "Home Weather" device: Observational Sensors, Binary Sensors, and Minute Forecast when enabled.

## Minute Forecast — Alpha, likely to change

> ⚠️ **Can take you over the 10,000 free API calls per month.** Cost depends on how much it rains, so it cannot be calculated in advance. Off by default.

A six-hour rain nowcast — when rain starts, when it stops, how much — on its own device. Google's endpoint is pre-GA, so the entities may change; each carries an `alpha` attribute.

| Entity | |
| --- | --- |
| Precipitation Starts In | minutes; attributes hold 15/30/60/120/360-minute rain totals |
| Precipitation Stops In | minutes; **unknown** when rain runs past the end of the forecast |
| Precipitation Rate | mm/h |
| Rain Next 60 Minutes | mm |
| Rain Rest Of Forecast | mm, plus a 15-minute timeline attribute |
| Precipitation Within The Hour | binary sensor |

Snow is not covered yet: rain totals filter on precipitation type, so snow reports nothing rather than something wrong.

**Resolution is Google's, not a setting.** Setup makes one call to measure your location's segment width, then offers only polling intervals that match it. Every onset reading publishes `onset_precision_minutes`, so a coarse answer never reads as a precise one.

### Cost

The daily or hourly forecast you already fetch is what starts and stops polling, so the gate is free. No rain forecast and it drops to about four calls a day; rain forecast and it watches closely; rain actually coming and it polls at your minimum whatever the forecast said, halving the gap as onset approaches.

| | 2 min | 3 min | 5 min | 15 min |
| --- | --- | --- | --- | --- |
| Dry month | 120 | 120 | 120 | 120 |
| 10 rain days | 1,480 | 1,080 | 750 | 410 |
| 20 rain days | 4,080 | 2,880 | 1,900 | 900 |
| 30 rain days | 7,920 | 5,520 | 3,570 | 1,590 |

A longer interval does not coarsen the forecast — every call returns all six hours — it only delays noticing a change.

A monthly ceiling (default 1,500) drops polling to two-hourly once reached. **A safeguard, not a guarantee:** it resets when Home Assistant restarts and cannot see other users of your API key. Set a quota cap in the Google Cloud console if staying inside the free tier matters.

## API Usage

Google allows **10,000 free calls per month** across all endpoints, then charges about $6.00 per 1,000. The coordinator ticks every minute but only calls an endpoint when its interval has elapsed, and serves cached data otherwise — including if the API errors.

Each endpoint has separate daytime and nighttime intervals. Nighttime defaults to 22:00–06:00 and is configurable.

| Endpoint | Day | Night | Calls/month |
| --- | --- | --- | --- |
| Current Conditions | 10 min | 30 min | ~3,360 |
| Daily Forecast | 30 min | 60 min | ~1,200 |
| Hourly Forecast | 20 min | 60 min | ~1,680 |
| Weather Alerts | 15 min | 30 min | ~2,400 |
| **Total** | | | **~8,640** |

Daily forecasts are always on. Hourly forecasts, alerts and the minute forecast are optional — disabling hourly saves ~1,680 calls/month and disabling alerts ~2,400.

The setup and options flows show an estimate before you commit, so adjust intervals there. If you need to cut usage, lengthen nighttime intervals first and daily forecasts second; both change little of value. Google Cloud Console → APIs & Services → Dashboard is the authoritative usage figure.

### Fetching a forecast on demand

`google_weather.get_forecast` fetches one forecast with a single call, so you can leave an endpoint disabled and still reach it from an automation:

```yaml
action: google_weather.get_forecast
data:
  entity_id: weather.home
  forecast_type: hourly   # daily, hourly or minute
```

## Examples

Notify on a severe weather alert, using the alert attributes:

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
          title: "⚠️ Severe Weather Alert"
          message: >
            {% set alerts = state_attr('binary_sensor.home_severe_weather_alert', 'alerts') %}
            {% for alert in alerts %}
            {{ alert.title }}: {{ alert.instruction }}
            {% endfor %}
```

Each alert in that `alerts` list carries `alert_id`, `title`, `event_type`, `area`, `severity`, `certainty`, `urgency`, `start_time`, `expiration_time`, `description` and `instruction`. The sensor itself also has `alert_count`, `max_severity` and `data_source`.

## Weather Alerts Coverage

Weather data works worldwide. Alerts do not: coverage varies by country, and the integration detects support on first setup. If the API returns a 404 for your location, only the Daytime binary sensor is created rather than three alert sensors that could never fire, and the log says so. Everything else works normally. See [Google's coverage list](https://developers.google.com/maps/documentation/weather/weather-alerts#data_sources).

Alert sensors sitting at "off" simply mean no alerts are currently active.

## Troubleshooting

- **API errors** — confirm the Weather API is enabled and the project has billing set up, then check Settings → System → Logs.
- **Entities missing** — check the integration loaded, then reload it or restart.
- **Only the Daytime binary sensor** — your region has no alert coverage; see above.
- **Wrong units** — units follow your Home Assistant setting; reload after changing it. Air pressure is always millibars, which is what the API returns regardless.

## Support

Issues and feature requests: [GitHub issue tracker](https://github.com/safepay/ha_google_weather/issues).

## License

MIT — see LICENSE.

## Credits

Uses the [Google Weather API](https://developers.google.com/maps/documentation/weather) from Google Maps Platform.

# Contributing to Google Weather Integration

Thank you for your interest in contributing to the Google Weather integration for Home Assistant!

## Development Setup

1. Fork the repository
2. Clone your fork: `git clone https://github.com/yourusername/ha_google_weather.git`
3. Create a new branch: `git checkout -b feature/your-feature-name`

## Directory Structure

```
ha-google-weather/
├── custom_components/
│   └── google_weather/          # Integration code
│       ├── __init__.py          # Integration setup
│       ├── manifest.json        # Integration metadata
│       ├── config_flow.py       # Configuration flow
│       ├── coordinator.py       # Data coordinator
│       ├── const.py             # Constants
│       ├── weather.py           # Weather entity platform
│       ├── sensor.py            # Sensor platform
│       ├── binary_sensor.py    # Binary sensor platform
│       ├── application_credentials.py
│       ├── strings.json         # UI strings
│       └── translations/
│           └── en.json          # English translations
├── README.md                    # Documentation
├── LICENSE                      # MIT License
├── hacs.json                    # HACS metadata
├── info.md                      # HACS info
└── .gitignore                   # Git ignore rules

## Code Style

- Follow PEP 8 Python style guide
- Use type hints for all function signatures
- Add docstrings to all classes and methods
- Keep lines under 100 characters when possible
- Use meaningful variable and function names

## Testing

Before submitting a PR:

1. Test the integration in Home Assistant
2. Verify config flow works correctly
3. Test options flow updates
4. Check all sensors and entities appear correctly
5. Verify smart polling works as expected
6. Test with both Metric and Imperial units

## Pull Request Process

1. Update the README.md if adding features
2. Update manifest.json version following semantic versioning
3. Add your changes to the commit message
4. Create a pull request with a clear description
5. Link any related issues

## Code Review

All submissions require review. We'll provide feedback on:

- Code quality and style
- Integration with Home Assistant
- Performance and API usage
- User experience
- Documentation

## Reporting Issues

When reporting issues, include:

- Home Assistant version
- Integration version
- Error messages from logs
- Steps to reproduce
- Expected vs actual behavior

## Feature Requests

We welcome feature requests! Please:

- Check existing issues first
- Describe the use case
- Explain expected behavior
- Consider API usage implications

## Questions?

Open an issue with your question or discussion topic.

Thank you for contributing! 🎉

# SaansSaathi

Every school morning, SaansSaathi reads the air forecast for a school's hours, turns it into a plan for the day (assembly indoors, PE moved to the cleanest hour, windows closed during the peak), sends it to the principal for one-tap approval, then sends parents a short Hindi voice note, and counts child-hours of outdoor exertion moved out of bad air.

Built for the WeMakeDevs x AWS "Environmental Hacks" hackathon (Air track).

Work in progress. See [PLAN.md](PLAN.md).

## Quick start

```sh
uv sync
uv run python -m saans.plan --school demo-1 --replay 2024-11-18
uv run pytest
```

## Built with AI assistance

This project was built with help from Claude Code (Anthropic).

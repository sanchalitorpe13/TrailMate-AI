# Contributing to TrailMate AI

Thanks for helping people spend a little less time on screens and a little more time outside.

## Set up

Follow the Windows (or any OS) installation steps in the README, then run:

    python -m pytest -v

All tests must pass without Ollama, Gemma or internet access.

## Ground rules

These keep TrailMate trustworthy:

1. **Be honest.** Never label fallback output as AI output. Never imply live weather, maps, GPS or wildlife data unless a feature really provides it. Keep self-reported and verified activity clearly separate.
2. **Stay private.** No analytics, tracking or third-party requests by default. Any network feature must be opt-in and clearly labelled.
3. **Stay safe.** Missions must never suggest trespassing, entering unsafe places, approaching or feeding wildlife, or eating wild plants. If you change prompts or the safety filter, add tests.
4. **Stay light.** Prefer the standard library. Justify any new dependency in your pull request.
5. **Stay accessible.** Keep keyboard navigation, visible focus, labels and reduced-motion support working.

## Workflow

1. Fork the repository and create a branch: `git checkout -b my-change`
2. Make your change, with tests for new behaviour. Tests must mock the AI layer.
3. Run `python -m pytest -v`.
4. Open a pull request describing what changed and why.

## Code style

- Routers parse HTTP only. Business logic goes in `app/services/`. SQL stays parameterized.
- Keep JSON field names consistent between `app/schemas.py` and `static/app.js`.
- Frontend text from users or the model must be inserted with `textContent`, never `innerHTML`.

## Reporting problems

Open an issue with your Windows/Python version, the exact command you ran, and the full error text. Please do not paste personal journal data.
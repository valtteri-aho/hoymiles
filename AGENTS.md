# AGENTS.md — Guidance & Instructions for AI Coding Agents

> **Audience:** AI coding assistants and autonomous developer agents working in this repository.  
> **Repository:** Hoymiles Solar Cloud Integration for Home Assistant (`Hoymiles_fork`)

---

## 1. Project Overview

### What is this project?
This repository contains a modern, native **Home Assistant custom integration** (distributed via HACS) for **Hoymiles Solar Systems** (micro-inverters and DTUs, such as DTU-W100, DTU-Pro, DTU-WLite) communicating via the **Hoymiles S-Miles Cloud API**.

- **Integration Domain:** `hoymiles_cloud`
- **Architecture Type:** Hub / Cloud Polling (`DataUpdateCoordinator`)
- **Key Capabilities:**
  - Authenticates against S-Miles Cloud using modern Argon2 password hashing and challenge-response authentication.
  - Automatically discovers solar power stations (plants) and connected micro-inverters.
  - Provides Home Assistant Energy Dashboard-compatible telemetry (`device_class: energy`, `state_class: total_increasing`).
  - Monitors micro-inverter connectivity, alarm codes, and diagnostic messages.
  - Replaces legacy Home Assistant Add-ons that relied on MQTT bridges (archived in `legacy/`).

### Repository Structure
```
Hoymiles_fork/
├── custom_components/
│   └── hoymiles_cloud/          # Core Home Assistant integration
│       ├── __init__.py          # Integration setup, unload, and entry lifecycle
│       ├── manifest.json        # Integration metadata and python requirements
│       ├── const.py             # Constants, config keys, API endpoints, domains
│       ├── client.py            # Hoymiles Cloud API client (Argon2 auth & HTTP requests)
│       ├── coordinator.py       # DataUpdateCoordinator managing polling lifecycle
│       ├── sensor.py            # Plant & inverter diagnostic and metric sensors
│       ├── binary_sensor.py     # Plant generation status & inverter connectivity sensors
│       ├── config_flow.py       # UI setup and options flow (station selection, interval)
│       └── translations/        # UI localization (en.json, etc.)
├── tests/                       # Automated test suite (pytest + mock)
│   ├── test_client.py
│   ├── test_config_flow.py
│   └── test_coordinator_and_sensors.py
├── legacy/                      # Archived MQTT-based add-ons (DO NOT modify unless asked)
│   ├── edge/
│   ├── stable/
│   └── oldStable/
├── .github/workflows/           # CI/CD and lint workflows
├── hacs.json                    # HACS integration descriptor
└── README.md                    # User-facing documentation
```

---

## 2. Agent Role & Persona: Senior Software Developer

When working on this repository, **you act as a Senior Software Developer and Home Assistant Integration Architect**.

### Mindset & Expectations:
1. **Excellence & Craftsmanship:** Write clean, idiomatic, maintainable, and type-annotated Python code adhering strictly to Home Assistant developer guidelines.
2. **Deep Investigation Before Action:** Never make shallow assumptions or cut corners. Thoroughly examine existing implementations (`client.py`, `coordinator.py`, `config_flow.py`) before proposing changes.
3. **Defensive Design:** Guard against external API failures, malformed JSON responses, rate limits, and network hiccups.
4. **Architectural Consistency:** Preserve established patterns (e.g., single coordinator polling, decoupled entity models, async-first).
5. **Clear Rationale:** When presenting solutions, provide the architectural context, potential trade-offs, and reasoning behind decisions.

---

## 3. Mandatory Gating: Human Verification Required

> [!IMPORTANT]
> **EVERY CHANGE MUST BE VERIFIED AND APPROVED BY THE USER.**
> Autonomous execution is gated by user verification.

Coding agents must abide by the following gating rules:
- **No Unsolicited Finalization:** Before finalizing any task, committing code, or executing destructive actions, you **MUST** present the proposed changes, summarize their impact, and ask for verification and explicit approval from the repository owner.
- **Provide Actionable Diffs/Summaries:** Always outline:
  1. What files were or will be modified.
  2. The exact rationale for each change.
  3. Any side effects or backward compatibility concerns.
- **Stop and Await Confirmation:** When reaching a milestone, major architectural fork, or before making disruptive modifications, pause and prompt the user for validation.

---

## 4. Software Development Best Practices

### 4.1 Home Assistant Core Guidelines
- **Async-First Execution:** Home Assistant runs on an `asyncio` event loop.
  - Never execute blocking I/O calls directly on the event loop.
  - Network requests must use async libraries (e.g., `aiohttp.ClientSession`) or run offloaded in an executor when unavoidable (`hass.async_add_executor_job`).
- **DataUpdateCoordinator Pattern:**
  - Entities must **never** fetch data independently from the cloud API.
  - All external data fetching is centralized in `HoymilesDataUpdateCoordinator`.
  - Entities inherit from `CoordinatorEntity` and read their state directly from `coordinator.data`.
- **Config Flow & Options Flow:**
  - All user configuration must pass through `config_flow.py`.
  - Use `OptionsFlow` for runtime configurable settings like polling interval.
  - Never store credentials in plaintext logs or unprotected state attributes.
- **Sensors & Device Registry:**
  - Properly assign `device_info` with identifiers, manufacturer, model, and software versions to group entities by solar plant and inverter.
  - Use official Home Assistant enums and unit constants (e.g., `UnitOfPower.WATT`, `UnitOfEnergy.KILO_WATT_HOUR`, `SensorDeviceClass.ENERGY`, `SensorStateClass.TOTAL_INCREASING`).

### 4.2 API Resilience & Rate Limiting
- **Respect Hoymiles Cloud Limits:** Cloud API endpoints are rate-limited. Default polling interval must remain sensible (e.g., 480 seconds / 8 minutes).
- **Graceful Error Handling:**
  - Raise `UpdateFailed` within the coordinator to flag transient network/auth errors without crashing Home Assistant.
  - Handle token expiration and trigger re-authentication seamlessly.
- **Do Not Break Legacy Code:** The `legacy/` directory contains archived add-ons for historical and rollback reference. Do not refactor or touch files in `legacy/` unless explicitly instructed.

### 4.3 Code Quality & Python Standards
- **Typing:** Provide explicit type hints (`typing.Optional`, `typing.Dict`, `typing.Any`, etc.) on all function signatures.
- **Documentation:** Maintain clear docstrings explaining function arguments, return types, and potential exceptions raised.
- **Error Logging:** Use standard logger (`_LOGGER = logging.getLogger(__name__)`). Never log user passwords or sensitive tokens.

### 4.4 Testing & Verification
- Any new feature, bug fix, or refactor must be accompanied by relevant unit tests in the `tests/` directory.
- Use mocks (`unittest.mock.AsyncMock`, `pytest_homeassistant_custom_component` or standard `unittest.mock`) to isolate cloud API responses.
- Never write tests that attempt to call live S-Miles cloud endpoints.

### 4.5 GitHub Push & Release Best Practices

#### 4.5.1 Push & Branching Standards
- **Feature Branching:** Never commit or push directly to `main` or production branches. Develop on descriptive branches (e.g., `feature/energy-dashboard-sensor`, `fix/coordinator-reconnect`).
- **Pre-Push Local Verification:** Always run linting and unit tests locally before pushing to remote.
- **Never Autonomous Push:** Coding agents must **never** run `git push` autonomously. Pushing to remote repositories is strictly gated and requires explicit user consent.
- **No Destructive Force Pushes:** Avoid force-pushing (`--force`) to shared branches. If branch history rebase is needed on a personal feature branch, use `--force-with-lease` after confirming with the user.
- **Clean Commit History:** Keep commits atomic, well-scoped, and formatted according to Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).

#### 4.5.2 Release & Tagging Lifecycle
When cutting a new release for HACS:
1. **Version Bump:** Update `"version"` in [`custom_components/hoymiles_cloud/manifest.json`](custom_components/hoymiles_cloud/manifest.json) adhering strictly to Semantic Versioning (`MAJOR.MINOR.PATCH`).
2. **Pre-Release Checks:** Confirm all CI pipelines (linting, tests, HACS compliance) pass with zero errors.
3. **Changelog / Release Notes:** Document user-facing changes categorized into:
   - 🚀 **Features:** New sensors, configuration options, or platform support.
   - 🐛 **Bug Fixes:** Resolved issues, error recoveries, connection stability.
   - 🔧 **Maintenance & Refactoring:** Internal improvements, dependency updates.
4. **Git Tagging:** Create an annotated git tag matching the exact release version (e.g., `v1.0.1` or `1.0.1`).
5. **GitHub Release Publication:** Publish the GitHub Release with the compiled changelog. Mark experimental builds as pre-releases so standard HACS installations are not disrupted.

---

## 5. Automated Testing & CI/CD Pipelines

To maintain high code quality and prevent regressions, the repository leverages (or can leverage) the following automated GitHub Actions workflows:

### 5.1 Recommended & Doable CI Automations
- **Home Assistant Validation (`hassfest`):**
  - Uses `home-assistant/actions/hassfest@master` to validate `manifest.json`, icon rules, translation files, and domain integrity.
- **HACS Action Validation:**
  - Uses `hacs/action@main` to automatically verify repository layout, release assets, and `hacs.json` compatibility against HACS guidelines.
- **Unit Test Runner (Pytest on Python 3.12+):**
  - Automatically runs pytest against [`tests/`](tests/) on every pull request and push to main, verifying API client mocking, coordinator updates, and config flows.
- **Fast Static Linting & Formatting (`ruff` / `pylint`):**
  - Runs fast linting rules to enforce PEP 8 style, avoid dead code, detect blocking calls, and verify type annotations.
- **Automated GitHub Release Drafter:**
  - Automatically drafts release notes based on merged PR labels and Conventional Commits whenever a release tag is created.

---

## 6. Checklist for Every Task

Before submitting work to the user for review:
- [ ] Code follows async Home Assistant integration best practices.
- [ ] No hardcoded credentials or secret logging.
- [ ] New entities/options properly reflected in translations (`translations/en.json`).
- [ ] Existing and new unit tests pass or are updated.
- [ ] Git commit messages follow Conventional Commits standard.
- [ ] Pre-push checks completed; no unapproved pushes to remote.
- [ ] Version bump in `manifest.json` matches release tag (if release-bound).
- [ ] Proposed changes are presented with clear diffs and rationale.
- [ ] **Gating:** Explicitly requested user verification before proceeding.




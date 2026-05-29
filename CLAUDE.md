# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

NeCTAR Tools is a collection of operational command-line tools for running the
NeCTAR Research Cloud (an OpenStack-based research cloud). Each tool is exposed
as a `console_scripts` entry point in `setup.cfg` (e.g. `nectar-allocation-audit`,
`nectar-pt-expiry`, `nectar-allocation-provisioner`). The package is `nectar_tools`.

## Commands

Tests, linting, and coverage are run through **tox** (uses `stestr` as the test
runner, configured in `.stestr.conf`):

```bash
tox                          # run the full default envlist: pep8, py312, functional, cover
tox -e py312                 # unit tests only (./nectar_tools/tests/unit)
tox -e functional            # functional tests (./nectar_tools/tests/functional)
tox -e pep8                  # style checks — runs pre-commit on all files
tox -e cover                 # unit + functional with coverage; fails under 90%
```

Run a single test or subset by passing a regex to stestr via posargs:

```bash
tox -e py312 -- nectar_tools.tests.unit.test_utils
tox -e py312 -- test_get_compute_zones_national
```

Linting is driven by **pre-commit** (`.pre-commit-config.yaml`), not raw flake8.
It runs ruff (format + lint, line length 79, see `pyproject.toml`), OpenStack
`hacking` with import-order checks, doc8, and `typos`. Run directly with:

```bash
pre-commit run --all-files
```

## Architecture

The codebase is organised into subsystems, each typically with a `cmd/`
directory holding the CLI entry points, plus manager/notifier/auditor logic:

- **`audit/`** — read-and-repair auditors. One subpackage per OpenStack service
  (`compute`, `network`, `image`, `identity`, `coe`, `loadbalancer`, etc.).
  Auditors subclass `audit/base.py:Auditor`. The runner (`Auditor.run_all`)
  introspects the class: **every public method that isn't in `BASE_METHODS`
  (`setup_clients`, `run_all`, `repair`, `summary`) is treated as a "check" and
  invoked automatically.** CLI commands in `audit/cmd/` subclass
  `audit/cmd/base.py:AuditCmdBase`, declare an `AUDITORS` list, and support
  `--check module:Class.method` to run a single check, `--list`, and `--limit`.
- **`expiry/`** — resource/allocation/account/image expiry. State machine logic
  in `expiry/expirer.py`; valid states in `expiry/expiry_states.py`; archiving in
  `expiry/archiver.py`. Commands in `expiry/cmd/`.
- **`provisioning/`** — allocation provisioning and quota reset
  (`provisioning/manager.py`, `provisioning/cmd/`).
- **`reports/`** — usage/SU reporting (`reports/manager.py`).
- **`cli/`** — standalone one-off tools (magnum/trove upgrades, warre
  maintenance, resource capacity, etc.) that don't fit the audit/expiry pattern.
- **`common/`** — shared logic such as `service_units.py`.

### Cross-cutting infrastructure (top level of `nectar_tools/`)

- **`auth.py`** — central factory for all OpenStack service clients (nova,
  keystone, neutron, glance, magnum, allocation client, openstacksdk, etc.).
  `get_session()` builds the keystone session; per-service `get_*_client(sess)`
  helpers wrap it. Most subsystems take a `ks_session` and call these helpers.
- **`config.py`** — config + CLI argument handling. `CONFIG` (a `Config`
  singleton) reads an ini file (default `/etc/nectar/tools.ini`) into an
  attribute-accessible dict, and also exposes `OSLO_CONF` (oslo.config). The
  `@configurable(section, env_prefix=...)` decorator injects config values as
  function defaults (used heavily in `auth.py`).
- **`cmd_base.py:CmdBase`** — base for command classes. Wires up the arg parser,
  logging, oslo config, and a keystone session. **Tools default to dry-run; the
  `-y/--no-dry-run` flag is required to perform real actions.** Honour this
  pattern (`self.dry_run`) in any new command.
- **`notifier.py`** — base `Notifier` that renders Jinja2 templates from
  `nectar_tools/templates/<dir>/` and sends via Freshdesk. Subsystems have their
  own notifier subclasses (`expiry/notifier.py`, `provisioning/notifier.py`).
  Slack notifications for audits go through `audit/cmd/slack.py` and the
  `slack_context` context manager.

### Tests

Tests live in `nectar_tools/tests/{unit,functional}` and use `testtools.TestCase`
via `nectar_tools/test.py:TestCase`, which loads the fixture config from
`nectar_tools/tests/nectar-tools.conf`. Fakes/mocks are in `tests/fakes.py` and
`tests/functional/fake_clients.py`. The default stestr path is the unit tests;
the `functional` tox env overrides `OS_TEST_PATH`.

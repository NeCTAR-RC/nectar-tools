# Nectar Tools

A collection of operational command-line tools for running the
[Nectar Research Cloud](https://ardc.edu.au/services/ardc-nectar-research-cloud/),
an OpenStack-based research cloud operated by ARDC.

Each tool is installed as a console script (see `setup.cfg` for the full
list), covering day-to-day cloud operations such as:

- **Auditing** — read-and-repair checks against OpenStack services
  (`nectar-compute-audit`, `nectar-network-audit`, `nectar-image-audit`,
  `nectar-identity-audit`, and friends)
- **Expiry** — allocation, project trial, image, and account expiry
  workflows (`nectar-allocation-expiry`, `nectar-pt-expiry`,
  `nectar-image-expiry`, `nectar-account-expiry`, ...)
- **Provisioning** — allocation provisioning and quota management
  (`nectar-allocation-provisioner`, `nectar-allocation-reset-quotas`)
- **Reporting** — service unit and usage reports (`nectar-su-reports`,
  `nectar-resource-capacity`)
- **One-off operational tools** — Magnum/Trove upgrade helpers, Warre
  maintenance, Freshdesk outbound email, and more.

Free software, licensed under GPLv3+.

## Prerequisites

- Python 3.8 or later (3.12 is used in CI)
- The `cryptography` Python package is a dependency; on some Linux
  platforms building it requires `pkg-config` (and typically a compiler
  toolchain and Python development headers) to be installed.

## Quickstart

### Install into a virtualenv

```bash
git clone https://github.com/NeCTAR-RC/nectar-tools.git
cd nectar-tools

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install .
```

For development, install in editable mode instead:

```bash
pip install -e .
```

### Configure

The tools read an ini-style configuration file, by default from
`/etc/nectar/tools.ini`. An alternative path can be given with
`-c/--config`. A starting point is provided in
[etc/example.conf](etc/example.conf); its sections configure the
Freshdesk notifier, the allocation system API, Sentry/GlitchTip error
reporting, logging, and per-tool settings.

The tools need OpenStack admin credentials, which are usually supplied
via the standard `OS_*` environment variables (e.g. by sourcing an
openrc file).

### Run a tool

All tools **default to dry-run mode**: they log what they *would* do
without making any changes. Pass `-y/--no-dry-run` to perform real
actions.

```bash
# Show what the compute auditor would do (dry run)
nectar-compute-audit -c etc/mycloud.conf

# List the individual checks an auditor provides
nectar-compute-audit --list

# Run a single check (module:Class.method), for real
nectar-compute-audit -c etc/mycloud.conf -y \
    nectar_tools.audit.compute.instance:InstanceAuditor.check_instance_states
```

Common flags supported by all tools:

| Flag | Description |
|------|-------------|
| `-c`, `--config` | Path to the configuration file (default `/etc/nectar/tools.ini`) |
| `-y`, `--no-dry-run` | Perform real actions instead of only reporting them |
| `-d`, `--debug` | Show debug logging |
| `-q`, `--quiet` | Don't print anything to the console |
| `--use_syslog` | Log to syslog |

## Architecture overview

The `nectar_tools` package is organised into subsystems, each with a
`cmd/` directory holding its CLI entry points:

| Directory | Purpose |
|-----------|---------|
| `nectar_tools/audit/` | Read-and-repair auditors, one subpackage per OpenStack service. Auditors subclass `audit/base.py:Auditor`; every public method is automatically discovered and run as a "check". |
| `nectar_tools/expiry/` | Resource, allocation, account, and image expiry. State machine in `expiry/expirer.py`, archiving in `expiry/archiver.py`. |
| `nectar_tools/provisioning/` | Allocation provisioning and quota reset. |
| `nectar_tools/reports/` | Usage and service-unit reporting. |
| `nectar_tools/cli/` | Standalone one-off tools that don't fit the audit/expiry pattern. |
| `nectar_tools/common/` | Shared logic (e.g. service unit calculations). |

Cross-cutting infrastructure lives at the top level of the package:

- **`auth.py`** — factory for all OpenStack service clients; most code
  takes a keystone session and calls the `get_*_client()` helpers.
- **`config.py`** — configuration and CLI argument handling
  (`CONFIG` singleton plus oslo.config).
- **`cmd_base.py`** — base class for commands; wires up argument
  parsing, logging, config, the keystone session, and the dry-run flag.
- **`notifier.py`** — renders Jinja2 templates from
  `nectar_tools/templates/` and sends notifications via Freshdesk.
- **`sentry.py`** — optional error reporting to GlitchTip/Sentry,
  enabled by setting a `dsn` in the `[sentry]` config section.

## Development

### Running the tests

Tests, linting, and coverage are run through [tox](https://tox.wiki/)
(with [stestr](https://stestr.readthedocs.io/) as the test runner):

```bash
pip install tox

tox                # full default envlist: pep8, py312, functional, cover
tox -e py312       # unit tests only
tox -e functional  # functional tests
tox -e pep8        # style checks (runs pre-commit on all files)
tox -e cover       # unit + functional with coverage; fails under 90%
```

Run a single test or subset by passing a regex to stestr:

```bash
tox -e py312 -- nectar_tools.tests.unit.test_utils
tox -e py312 -- test_get_compute_zones_national
```

### Linting

Linting is driven by [pre-commit](https://pre-commit.com/): ruff
(format + lint), OpenStack `hacking` import-order checks, doc8, and
`typos`. To run it directly (and optionally install it as a git hook):

```bash
pip install pre-commit
pre-commit run --all-files
pre-commit install
```

## License

GPLv3+ — see [LICENSE](LICENSE).

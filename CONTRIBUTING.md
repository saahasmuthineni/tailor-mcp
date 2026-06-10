# Contributing

> **A note on authorship.** This project is maintained by a solo non-technical founder working with Claude and close friends. The architecture is intentional, the test suite is real, and the design decisions are documented in the ADRs — but code reviews, bug reports, and technical scrutiny are especially welcome given that context. If something looks wrong, it may well be.

Thanks for considering a contribution. This project is a governance-aware middleware layer that sits between structured data sources and LLMs; PRs are welcome for bug fixes, additional child MCPs (e.g. Notion exports, CSV directories, custom structured data), docs, and test coverage.

## Quick start

```bash
# Clone and install in dev mode
git clone https://github.com/saahasmuthineni/tailor-mcp.git
cd tailor-mcp
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Sanity checks

```bash
pytest -v                          # run tests (~250+ tests)
python tests/security_probe.py     # standalone security-gate probe
tailor --help               # CLI smoke test
tailor pilot --help         # verify the pilot wizard is wired
tailor status               # diagnostic smoke check
```

### Lint & format

```bash
ruff check src tests
ruff format src tests
```

CI runs `ruff check` and `ruff format --check`; both must pass.

## Branching

- `main` — stable, CI-green.
- Open PRs from a feature branch named `type/short-description` (e.g. `fix/oauth-port-mismatch`, `feat/notion-child`).

## Framework changes: open an issue first

Bug fixes, new children, examples, docs, and tests can go straight to
a PR. For changes under `src/tailor/framework/` (the router, security
pipeline, audit log, vault layer, interfaces), please **open an issue
describing the change before writing the PR**. The framework's
load-bearing behavior is governed by the ADRs in `docs/adr/`, and most
framework changes either interact with one or warrant a new one — a
short design discussion up front saves everyone a rewrite. This is
about sequencing, not gatekeeping: framework contributions are
welcome.

## Commit messages

Short imperative subject, optional body explaining *why*. Example:

```
Fix OAuth callback port drift in README

README troubleshooting cited port 8899 but wizard.py has used
8189 since v3. Anyone hitting "address in use" was checking
the wrong port.
```

## Adding a new child MCP

Children are the extension point of the framework. See [CLAUDE.md § "Adding a New ChildMCP (new data source)"](CLAUDE.md#adding-a-new-childmcp-new-data-source) for the contract. Minimum viable child:

1. Subclass `tailor.framework.ChildMCP`.
2. Implement `domain`, `display_name`, `consent_info`, `tool_definitions`, `param_schemas`, `execute`, `estimate_cost`.
3. Register it in `src/tailor/__main__.py::cmd_serve()` with `router.register_child(...)`.
4. Add tests next to the existing ones in `tests/`.

The router automatically generates `approve_consent_<domain>` and `revoke_consent_<domain>` tools — the child does not need to.

## Tests

- Unit tests live in `tests/` and are picked up by pytest's default discovery.
- `pytest-asyncio` is configured in `asyncio_mode = "auto"` — no explicit `@pytest.mark.asyncio` needed.
- Keep tests deterministic: seed any randomness, avoid network calls, avoid `time.time()` assertions (use monotonic offsets instead).
- Sleep-based tests (e.g. circuit-breaker cooldown) are already in the suite; prefer time injection over `time.sleep` for new tests.

## Security-sensitive changes

Changes that touch `framework/middleware.py`, `framework/router.py`, or any consent/cost/circuit logic should add or update cases in `tests/security_probe.py` in addition to pytest coverage. The probe is CI-required and pytest-free so it can run anywhere.

## Reporting bugs

Open an issue using the bug-report template. Include:
- Your OS and Python version
- Steps to reproduce
- Expected vs actual behavior
- Logs from `~/.tailor/logs/server.log` if relevant (redact anything personal)

## License

By contributing, you agree your contributions are licensed under the GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later), matching the project license. (Tagged releases through v8.0.0 remain Apache-2.0 in perpetuity for recipients who already received them; v9.0.0 onward is AGPL.)

## Developer Certificate of Origin (DCO)

Every commit must carry a `Signed-off-by` line certifying that you
have the right to submit the code under the project license — the
standard [Developer Certificate of Origin](https://developercertificate.org/)
used by the Linux kernel, GitLab, and many other projects. It is not
a copyright assignment and grants the project no rights beyond the
license above; it is a statement of provenance.

Sign off by committing with the `-s` flag:

```bash
git commit -s -m "Your message"
```

which appends a line like:

```
Signed-off-by: Your Name <you@example.com>
```

CI checks every PR commit for the sign-off and tells you exactly
which commits are missing it. Forgot one? `git commit --amend -s`
(or `git rebase --signoff main`), then update your branch with
`git push --force-with-lease`.

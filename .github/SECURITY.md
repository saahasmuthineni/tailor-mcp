# Security Policy

This project is local-first infrastructure for LLM-assisted analysis of
high-frequency biometric data. Security and data-governance issues are
treated as load-bearing bugs, not optional polish.

## Reporting a vulnerability

**Do not open a public issue** for anything in the following categories:

- Credential or token leakage paths (Strava OAuth secrets, audit DB
  paths, vault paths that might contain participant-identifying data).
- Bypass of any layer of the router security pipeline — `ParamValidator`,
  `CircuitBreaker`, `ConsentGate`, `CostGate`, `PHIScrubber`, `AuditLog`,
  `TokenLedger`.
- Any path that lets a downstream LLM client read participant data at a
  higher tier than it was granted consent for.
- PHI that appears in a log file, audit row, or vault note under any
  documented code path.

Use GitHub's **private vulnerability reporting** to file a report:
<https://github.com/saahasmuthineni/tailor-mcp/security/advisories/new>.

Expect an initial acknowledgement within a few days. Triage and fix
timelines depend on severity and reproducibility — there are no
blanket SLAs on a personal research repository.

## What to include

- Package version (`tailor --help` header, or commit SHA).
- OS + Python version.
- Minimal reproduction — ideally a test or a `security_probe.py`-style
  script that fails under the current code.
- What you believe the correct behavior is, and which layer of the
  pipeline should have caught it.
- If you are reporting an issue involving actual participant data:
  **do not include the data in the report**. Describe the shape
  instead.

## Scope

In scope:

- Anything under `src/tailor/`.
- The `tests/security_probe.py` standalone probe.
- The OAuth wizard (`wizard.py`) and its localhost callback server.
- CI workflow configuration that could leak a token or run attacker-
  controlled code.

Out of scope:

- Upstream Strava API vulnerabilities — report to Strava.
- Claude Desktop / Claude API behavior — report to Anthropic.
- Vulnerabilities in user-installed Obsidian vaults or Obsidian itself.
- Social-engineering scenarios that require physical access to the
  analyst's workstation.

## Dependency triage

Dependabot runs weekly for `pip` and `github-actions` ecosystems
(see `.github/dependabot.yml`). Security-flagged updates are merged
ahead of routine updates.

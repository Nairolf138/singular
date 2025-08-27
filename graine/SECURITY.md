# Security Policy

## Supported Versions

This prototype is under active development. Security fixes are applied only to
the latest commit on the main branch.

## Environment Restrictions

- No network access.
- No subprocess or foreign-function interface.
- File access is limited to the repository workspace.

## Patch Validation and Audit

All patches must pass validation before execution. Each run records a hash of
the inputs and results to facilitate later audit and forensic analysis.

## Reporting a Vulnerability

Please open an issue or contact the maintainers if you discover a security
problem. Do not disclose details publicly until a fix has been discussed.

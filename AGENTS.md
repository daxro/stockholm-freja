# Project Instructions

## Purpose

`stockholm-freja` is a narrow Python helper for the Stockholms stad Freja eID+
personnummer initiation and polling protocol.

## Contracts

- Keep the package scoped to the Freja step only.
- Do not add InfoMentor, Tempus, SAML, persistence, or CLI behavior.
- Never log or include personnummer, cookies, SAML values, authentication URLs,
  headers, or response bodies in exception messages or docs.
- Validate local input before network access.
- Preserve Python 3.10-compatible syntax.

## Development

- Run `uv lock --check`, `uv run --locked pytest`, and `uv build`.

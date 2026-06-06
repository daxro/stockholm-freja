# Stockholm Freja

Small Python helper for the Stockholms stad Freja eID+ personnummer login step.

It only performs the Freja initiation and polling protocol after a caller has
already navigated to a Stockholms stad Freja page. It does not implement
InfoMentor, Tempus, SAML, session persistence, or any CLI.

## Install

For a consumer project managed by uv:

```bash
uv add "stockholm-freja @ git+https://github.com/daxro/stockholm-freja.git"
```

Update a consumer project's locked dependency:

```bash
uv lock --upgrade-package stockholm-freja
uv sync
```

## Usage

```python
from stockholm_freja import freja_login

freja_login(
    session,
    freja_page_url,
    "YYYYMMDDNNNN",
    timeout=180.0,
    on_started=lambda: print("Approve the login in Freja eID+."),
)
```

The caller owns the surrounding authentication flow, user prompts, logging,
redaction, and session verification.

## Safety

Do not log personnummer, cookies, SAML values, authentication URLs, headers, or
response bodies. Exceptions raised by this package intentionally avoid those
values.

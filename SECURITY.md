# Security Policy

## Reporting a Vulnerability

**Please do not open a public issue for a security report.**

Report privately using GitHub's private vulnerability reporting: open a draft
advisory from the repository's
[Security tab](https://github.com/IBM/data-scout/security/advisories/new). This
reaches the maintainers privately and keeps the discussion attached to the
repository.

We will not publish or confirm a vulnerability until the report has been analysed
and a fix or mitigation is available. We will keep you updated while that work is
in progress, and we are glad to credit you in the resulting advisory unless you
prefer otherwise.

## Scope

This tool downloads and processes content from user-specified URLs. When exposed as
an API service, operators should:

- Enable API key authentication (`API_KEY` environment variable)
- Run behind a reverse proxy with rate limiting
- Restrict network egress if the service should not reach internal hosts
- Review the crawl-policy allow/deny lists before relying on them. They are not
  shipped: `src/processing/crawl_policy/` is empty on a fresh clone and is filled
  in at runtime by the LLM classifying each domain it encounters, so early runs
  have no policy to enforce

## Known and accepted exposures

These are documented rather than fixed. Reports about them are welcome as
discussion, but they are known and not treated as new vulnerabilities:

- **`REACT_APP_API_KEY` is embedded in the frontend bundle.** Create React App
  inlines `REACT_APP_*` variables at build time, so the key is readable by anyone
  who loads the page — and it is the same key that guards every API route. This is
  accepted because the tool is intended to run locally. Do not reuse a key that
  protects anything else, and do not serve the built frontend to untrusted users
  while relying on that key for access control.

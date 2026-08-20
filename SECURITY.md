# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly.

**Do not open a public issue.** Instead, email the maintainers at the address listed in the repository's GitHub settings or use GitHub's private vulnerability reporting feature.

We will acknowledge your report within 5 business days and aim to provide a fix or mitigation plan within 30 days.

## Scope

This tool downloads and processes content from user-specified URLs. When exposed as an API service, operators should:

- Enable API key authentication (`API_KEY` environment variable)
- Run behind a reverse proxy with rate limiting
- Restrict network egress if the service should not reach internal hosts
- Review the crawl-policy allow/deny lists before production use

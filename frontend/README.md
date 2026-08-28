# Data Scout frontend

React + TypeScript dashboard for submitting pipeline jobs and following them as
they run: live logs, live metrics, and the output files a finished run produced.

The [root README](../README.md) is the source of truth for running the stack;
this covers what is specific to working in `frontend/`.

## Commands

```bash
npm install
npm start                                          # dev server on :3000
CI=true npx react-scripts test --watchAll=false     # tests, as CI runs them
CI=true npx react-scripts build                     # production build
```

From the repo root, `make frontend` runs the dev server and `make build` does
`npm install` plus a production build.

Do not run `npm run eject`. It is irreversible and would replace the pinned
`react-scripts` setup that the Dockerfile builds against.

## Configuration

Set in `frontend/.env`:

- `REACT_APP_API_URL` — backend URL (default `http://localhost:8000`)
- `REACT_APP_API_KEY` — the backend's `API_KEY`, if one is set. **Not a secret.**
  Create React App inlines `REACT_APP_*` at build time, so this ends up as a
  literal string in `build/static/js/main.*.js` and anyone who loads the page can
  read it. See [Exposure](../README.md#exposure).

## Gotchas

**`react-scripts` is pinned at 5.0.1 and Create React App is deprecated** (Feb
2025), so this will need replacing eventually — Vite is the usual destination.
It does still work on current Node: verified compiling on Node 24, and the
Dockerfile builds it on `node:18-alpine`. If a future Node release breaks the
webpack 5 build, `NODE_OPTIONS=--openssl-legacy-provider` is the usual first
thing to try.

**`package-lock.json` is not committed** (`.gitignore`), so builds are not
reproducible and the Dockerfile uses `npm install` rather than `npm ci`. Do not
switch it to `npm ci` — it needs a lockfile that is not there.

**Jest and webpack disagree about which files exist.** Jest's
`moduleFileExtensions` ignore `tsconfig.json` while webpack's
`resolve.extensions` do not, so tests can pass green while the production build
is broken. Run the build, not just the tests, before opening a PR.

## Two limitations that look like frontend bugs

Both are in the [root README](../README.md#known-limitations):

- With `API_KEY` set, the live log and metrics WebSockets are rejected and the
  results ZIP download returns 401 — browsers cannot attach auth headers to a
  WebSocket handshake or to a download opened in a new tab. The UI reports this
  rather than retrying forever.
- The frontend container serves IPv4 only (`listen 80`), which is invisible
  behind a published port but unreachable on an IPv6-only network.

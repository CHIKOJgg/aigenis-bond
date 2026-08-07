# Frontend dependency audit exceptions

## react-router / react-router-dom (npm audit: high)

Current pinned version: `7.18.2`.

The npm advisory currently reports a high-severity React Router issue affecting
RSC/server-action request processing. This application is a client-only Vite
SPA: it does not use React Server Components, server actions, SSR hydration,
`createStaticRouter`, `ServerRouter`, or `ScrollRestoration`. The production
surface serves static assets from nginx and the API is a separate FastAPI
origin. The frontend CSP also restricts scripts to the application origin.

The advisory's suggested downgrade (`7.11.0`) is not an acceptable remediation:
the same audit database reports additional high-severity vulnerabilities in
that older range. Keep `7.18.2` pinned, re-check the advisory on every release,
and upgrade when a non-vulnerable SPA-compatible release is published. A
dependency upgrade remains a release gate if React Router server-side features
are introduced later.

# Vercel frontend

Use `frontend` as the project root. The repository configuration selects Vite,
runs `npm ci` and `npm run build`, and publishes `dist`.
[Vercel programmatic configuration](https://vercel.com/docs/project-configuration/vercel-ts)

Set `DATASLEUTH_API_ORIGIN` for the target Vercel environment to the exact
public HTTPS Render origin, for example `https://your-api.onrender.com`.
Use the origin without a trailing slash or path. Missing or invalid configuration
fails deployment configuration evaluation. The origin is a routing setting.
Keep database, storage, Redis and session credentials on the server.
Configure preview deployments with a separate test backend and its own
allowed browser origin.

Set the Render API's `BROWSER_ORIGIN` to the exact browser-facing Vercel origin.
The browser uses relative `/api/v1/*` requests. Vercel forwards those requests
to Render over HTTPS and serves frontend deep links through `index.html`.
The API preserves its exact-origin checks and sets host-only, Secure,
HttpOnly, SameSite=Strict session cookies. API responses carry `no-store` and
the rewrite disables Vercel CDN caching.
[Vercel external rewrites](https://vercel.com/docs/routing/rewrites)

Validate the deployed staging stack with a synthetic document. Check these
paths through the Vercel origin:

1. Open a protected deep link directly, sign in, and reload it.
2. Confirm the browser sets and sends the session cookie on `/api/v1` and
   that sign-out or session revocation returns the user to sign-in.
3. Check that a request with an unapproved Origin receives 403 and that
   an API response retains its status, media type and `no-store` headers.
4. Upload a synthetic file, scan it, inspect findings, and download a masked
   report. Verify that an upload at the configured file-size limit reaches
   Render through the deployed external rewrite.
5. Sign in with two independent sessions and confirm neither receives
   cached responses from the other.

The Vite preview proxy is useful for local regression checks. These staging
checks verify behaviour specific to Vercel's deployed edge and Render.

## Public release — 2026-11-16

The owner explicitly requested public access after repeated login failures. Netlify visitor access protection is disabled (no team SSO and no password). The Netlify entry point now starts local tools directly without an Identity login overlay.

Cloud endpoints accept only same-origin POST requests carrying the visitor’s own Google Colab/Drive token or Groq key. A SHA-256 credential digest supplies an isolation namespace, not a verified user account. Existing fixed-provider handlers authorize every operation against Google/Groq; malformed, expired or unauthorized grants fail. Client-supplied identity headers are stripped. No owner token, shared account or email allowlist is used. `/api/session` reports public access with `authenticated: false`.

27 focused tests passed (public access, own-grant handling, upstream rejection, same-origin enforcement, spoofed identity, Colab runtime isolation). Live Google processing still needs a real user grant; automated tests use synthetic grants and provider stubs. Historical private-login notes below are superseded by this explicit public release.

# MadarFiles: Netlify migration

Target project: `madarfiles` (`31cb569f-3ebf-426f-bcee-b3bbbb9f9f1c`). Team: `joo-9suc7au` on Free. The project was created owner-private; do not make it public until app login and invited users have been verified. The existing Sites deployment has not been changed.

## Prepared

- `npm run build:netlify` emits only browser assets to `netlify-public` (including the self-hosted FFmpeg runtime and caption fonts).
- `netlify/functions/api.mjs` ports existing Colab/Drive/Groq APIs to modern Netlify Functions. The Node WebSocket transport preserves the existing Jupyter acknowledgement protocol, does not follow redirects and enforces TLS.
- Authentication uses Netlify's verified private-project `context.user`. Client-sent Sites identity headers are discarded. Future public app login uses `@netlify/identity` and a server-side `MADAR_ALLOWED_EMAILS` allowlist; empty configuration denies access.
- The UI handles email/password login, invitation/recovery callbacks and enabled provider discovery. It does not auto-create accounts.
- Requests and processing continue using each visitor's own Google/Groq authorization. No owner Google token or service-account credential is bundled.
- Colab/Drive use 2 MiB transfer parts, below Netlify's buffered payload limit. The optional Groq route has a 4 MiB limit after local extraction on this target. The main Colab transcription tool remains available for large inputs.
- `.netlify` and the published asset directory are ignored by Git; CLI linking state and authorization do not ship in source or browser assets.

## Validation

94 JavaScript tests passed, including a real TLS WebSocket test (local test certificate explicitly trusted by the test child process); function compilation succeeded with Netlify CLI 27.19.0. Built function archive is approximately 1.9 MiB and public assets approximately 36 MiB. Owner Google/GPU execution and authenticated Netlify login are not yet verified. Anonymous checks against / and /api/session return the Netlify private-project 401 login perimeter.

## Remaining deployment and configuration

1. **Completed:** CLI authorization and production deployment. Deployment `6afa3439734d1471669b6d71` is ready at https://madarfiles.netlify.app, with the `api` function deployed. The CLI's explicit --site UUID lookup failed; the already linked project deployed successfully without that redundant flag. No plan or visitor-access setting was changed.
2. Add `https://madarfiles.netlify.app` to Authorized JavaScript origins of the existing Google OAuth web client in project `madarfiles`; test Google authorization and project-use permissions using a separate tester account.
3. Before family access, enable Identity in the project's dashboard, select invite-only registration, configure an explicitly approved allowlist and invite the selected users. Do not change project visibility until that setup is complete. On Free, Netlify private project access itself is owner-only; family login therefore requires the app-level Identity layer before changing the perimeter.
4. An attempt to persist the owner's email in `MADAR_ALLOWED_EMAILS` was rejected by automatic approval review pending explicit approval of the email and Netlify destination. No allowlist was configured. Do not retry or bypass that rejection.

Dashboard: https://app.netlify.com/projects/madarfiles

## Login routing correction

Production request logs showed `/api/session` returning 404 without function invocation while static assets loaded. Uploading the prebuilt ZIP directory did not preserve its custom routes. Deploy from the function source directory with `--skip-functions-cache`, so the CLI compiles and uploads custom path metadata. `npm run deploy:netlify` encodes the correct source path. Do not treat an API route 404 as an Identity account/password problem.

Correction deployment: `6afa3a095ee82e1646dd2d02` (ready). Netlify now reports `runtimeAPIVersion: 2` and an `/api/*` route for the API function; the previous deploy lacked both function routing/build metadata. The user reports the Google Cloud authorized origin has been updated. Authenticated owner login and Google processing still require live user verification.

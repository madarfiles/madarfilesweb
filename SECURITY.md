# Security boundaries
The public page intentionally has no Netlify Identity/dashboard login gate. Every Colab/Drive request carries the visitor's temporary OAuth token, and Groq uses their own key. Provider APIs enforce ownership; token hashes are cache namespaces, not verified identities. Wrong Origin and missing grants fail before provider access.

Only fixed provider APIs are proxied. Jupyter URLs/proxy credentials come from Google's authenticated runtime response, never a browser-supplied host. Runtime cache entries are bounded and isolated by token digest plus runtime name and expire after ten seconds. Revocation may therefore take this cache lifetime to stop previously delegated proxy access.

Source and result chunks are bounded and checksummed. Fixed filenames sit under validated UUID job folders. No arbitrary Python or shell code is accepted by the HTTP API. The worker has a service lock, job startup lock, serial queue and sanitized diagnostics.

Static/API headers are configured separately: the API is private no-store; the versioned FFmpeg engine under /runtime/<version>/ is cached immutably, pages and scripts revalidate, and framing by any other site is denied. No permissive CORS is emitted. Archive previews reject ZIP64/multipart/encrypted layouts and bound expanded text. User file names and text go to DOM text/value/canvas, not HTML insertion.

Direct dependencies are pinned and audited, and package-lock.json pins every transitive dependency; CI installs it with npm ci. Models, apt packages and Python dependencies are external supply-chain risks not covered by npm audit.

Do not put private media or tokens into public GitHub Issues. Contact the owner by an agreed private channel. No support email is embedded or report sent automatically.

Before broad release, test two real Google accounts in both directions for status, download and stop on disposable resources. CI uses synthetic grants and cannot replace that test. No test suite here is a comprehensive penetration test or absolute guarantee.

# MadarFiles Web 0.21 — orbital workspace and Colab tools

The owner-private Site now supports Google Identity Services token-model authorization using the owner's Web OAuth client and Google Cloud project `madarfiles`. Tokens stay in page memory, use only the `colaboratory` scope, and are passed in HTTPS POST bodies to Madar (never custom headers recorded by request logs), then in Authorization headers to the fixed Colab API. No client secret, refresh token, Google password, Drive scope, public tunnel, or browser-local music separation is used.

## Google setup

- Web OAuth client: `186468726329-rr3ehnmr9grubdhftbjdos2od25jv4j0.apps.googleusercontent.com`.
- Authorized JavaScript origin: `https://madar-family-web.s44107277students.chatgpt.site`.
- Colab API must be enabled and permitted for `madarfiles`. The selected Google account must have project-use permission, OAuth test-user access where applicable, an eligible paid Colab/Google AI entitlement and positive compute-unit balance.
- No billing plan is activated by this code. Account eligibility is queried; compute balance is not exposed by the subscription endpoint and must be checked inside Colab.

## Execution

1. Explicit Google consent, read-only subscription/GPU eligibility/session discovery.
2. Explicit upload/compute consent, idempotent runtime assignment (`madarweb-<uuid>`) with T4 first.
3. Authenticated Jupyter API fetched from the matching `runtimes.get` response; OAuth bearer is never sent to the runtime host. Redirects are refused.
4. Source transferred as 2 MiB parts, verified with a SHA-256 digest of concatenated part SHA-256 digests. Maximum upload 512 MiB; no duration cap.
5. A fixed reviewed runner is launched through a Jupyter websocket. A filesystem lock prevents double launch. No arbitrary Python code/path/URL proxy is exposed to the browser.
6. Pinned `audio-separator[gpu]` and ONNX CUDA libraries, actual CUDA probe, existing UVR chunk/checkpoint engine. Periodic status reports use measured chunk timings; startup has no invented ETA.
7. Output M4A or optional MKV, max 256 MiB, downloaded as checksummed parts and added to local session results. User downloads to the device, then explicitly deletes the GPU session. Closing the tab does not delete the session. Colab may terminate runtimes under its own limits.

Nonsecret session identifiers and config are saved locally for recovery. After refresh, reauthorize Google, then recover the job/result or stop the runtime. Session discovery recovers Madar web runtimes even if local metadata was lost. Partial uploads need a fresh job. Tokens expire and may require reauthorization before a long job's result can be downloaded.

## Validation

`npm run build`, `npm test`, and `python -m unittest discover -s tests -p 'test_*.py'` cover authorization boundaries, fixed destinations, Jupyter acknowledgements, assignment IDs, corrupt transfers, duplicate job launch, and existing media/PDF/subtitle tools. GPU execution, the owner's Google grant, and physical iPhone behavior require a live account/device test; they have not been verified in the development session.

All other tools remain: local image/PDF/audio/video conversion, QR and subtitles; opt-in Groq transcription/translation. Site sharing remains owner-only.

0.5.1 fixes incoming Request.signal compatibility on hosted Workers, uses an explicitly managed timeout/cancellation signal, and includes safe stage/error codes. OAuth credentials are excluded from request-header metadata.

0.5.1 replaces unsupported Worker Fetch redirect:error with redirect:manual plus explicit 3xx refusal on control-plane, Jupyter REST and websocket startup calls. A regression probe in tests/workerd-check.mjs was executed under workerd 2026-11-14 (compatibility date 2024-09-23): it reproduced the unsupported option TypeError, completed all three fixed eligibility requests and rejected a redirect without a second request. Provider responses in this probe are synthetic; the real owner account still requires verification.

0.5.1 adds the authenticated runtime Origin header on kernel websocket startup, default-protocol binary message decoding, bounded reconnection with refreshed connection info, and authoritative REST startup confirmation after a dropped websocket. Existing uploaded jobs can recover their validated server-side config and a healthy kernel without re-uploading. Runner files are upgraded in place only before a job has published a status. The job directory is based on its script path, not a hard-coded kernel working directory.

## Version 0.5.1

- Inline result playback and a device-download link inside the Colab tool; the session Results list remains available. Preview blob URLs are revoked on tool disposal, and repeated download clicks within the same tool reuse the local completed result.
- Explicit full-clip default or a selected portion. Times are entered as minutes or m:ss, with Arabic/Persian digits supported. Only the API continues to use seconds.
- Music removal appears in both Audio and Video filters; the video workspace also forwards its selected file to separation.
- Public-link downloader uses an eligible CPU runtime, not a GPU. Only recognized single-video HTTPS URLs from YouTube, TikTok, X/Twitter and Instagram are accepted; account and playlist URLs are rejected. No platform login/cookies or DRM bypass are provided.
- Pinned yt-dlp 2026.10.26, native network downloads, public-IP DNS checks for connection targets, explicit byte limits, local MP4 re-encoding with FFmpeg, and checksummed result transfer. Protected/live/private/blocked platform access fails with a clear message.
- Local validation: 41 JavaScript tests, 9 Python tests, browser checks for Video categorization, full/partial duration controls and downloader UI. The pinned downloader initialized and re-encoded a synthetic local MP4. External downloads from each platform and physical iPhone behavior have not been verified.
- This is a private utility with limited permissions, not a security certification or penetration-test report. No absolute device-safety guarantee is made. Uploaded media is processed at Google; downloads may be retained by the user's device. Heavy files can exceed browser memory limits.

## Result transfer acceleration (0.5.1)

Result chunks now transfer as binary response bodies to the browser, with up to three in-flight requests rather than a sequential Base64 JSON loop. Legacy JSON requests remain supported for open older pages. SHA-256 and exact per-part size checks still precede assembly; partial verified parts stay in page memory for retries and are discarded on completion, stop or closing the tool. Transient network/server/rate-limit errors retry a bounded number of times. Speed and remaining-time estimates use observed verified bytes.

Regression coverage includes out-of-order arrivals, a strict three-request concurrency limit, damaged-part replacement, interrupted transfers, page-memory retry reuse, cancellation and legacy/binary response compatibility. The actual user's new end-to-end speed has not yet been measured; no fixed speedup is promised.


## 0.5.2 — GPU and reduced preparation time

New URL-download sessions select T4 GPU by default, with L4 and an explicit CPU alternative. NVENC is selected only after an actual one-frame encoding probe; a GPU allocation alone is not treated as proof of encoder availability. Compatible H.264/AAC sources are remuxed without re-encoding their video or audio; this preserves the existing encoded streams. Conversion uses NVENC when available and reports CPU fallback when necessary. Partial-video separation output also tries verified NVENC; full-video output continues copying the video stream.

The URL downloader reuses resolved metadata instead of extracting it twice, downloads media fragments with four bounded workers, and throttles progress writes. Binary result transfers try the authenticated Jupyter raw-file route first. Unsupported routes, login/redirect responses or transient failures fall back to the existing Contents API without following a redirect. SHA-256 verification in the browser remains mandatory, and Google OAuth never reaches the runtime host or browser result URLs.

Validated: JavaScript regression tests for direct-file delivery/fallback, Python tests for NVENC probe/selection/fallback and copy mode, plus real local FFmpeg remux with identical video packet SHA-256 hashes. Live NVENC execution in the owner's Colab account and live raw-file route throughput remain unverified. GPU can accelerate processing but is not represented as increasing the user's network bandwidth.


## 0.6 — orbital workspace and cloud catalog

All 23 tools use the same responsive orbit, including every category and QR. Six tools are displayed per page; labels remain upright, horizontal drag rotates, paging reaches the rest, keyboard focus/hover pauses movement, and reduced-motion preference disables automatic rotation. The mobile hero is compact.

Ten fixed Colab tasks are added: EasyOCR image/PDF OCR, IS-Net background removal, editable PDF-to-DOCX conversion, Whisper transcription to TXT+SRT, NLLB text/subtitle translation with protected-name mappings, SRT burn-in, media conversion/compression, proportional portrait/landscape/square resizing, experimental SD-Turbo image generation, and experimental silent Wan short-video generation. All use the existing authenticated runner and checksummed transfer; no arbitrary user code, shell command or model ID is accepted. Model downloads happen on the user's runtime. PDF tasks are limited to 20 pages.

Video generation requests eligible high-memory L4/A100 resources and is labelled experimental. Image generation is also experimental. Generated results are checked before delivery. NLLB loads the verified official safetensors revision 38bd1c6a0f58097b26ef7c7cd73a0dcac034350a with remote code disabled. Optional name mappings preserve named spans but can affect translation fluency. Review translated and religious text.

NVENC diagnostics distinguish missing encoder build, driver libraries, driver API incompatibility and unavailable GPU encoder. Download selection prefers H.264 sources to avoid unnecessary transcoding. No app can guarantee NVENC on every Colab allocation. CPU fallback remains explicit. A GPU does not increase internet bandwidth.

Local validation: actual editable DOCX conversion of a synthetic PDF; actual FFmpeg subtitle burn, MP4 conversion and blurred-background resize; 53 JavaScript and 18 Python regression tests. Browser QA confirmed orbit rendering, category changes, QR and cloud-tool forms. Physical iPhone behavior and live cloud model/GPU execution in the owner's account remain unverified. Only session/allocation identifiers are stored in localStorage; prompts, subtitles, uploaded content, and OAuth tokens are not persisted there.


## 0.7 — compatibility and persistent session

Fix confirmed dependency resolution failures: rembg 2.0.87 requires ONNX Runtime >=1.23.2 and NumPy >=2.3, conflicting with the old GPU pin. Use the compatible rembg 2.0.67 / ORT GPU 1.23.2 / NumPy 2.2.6 stack. Install faster-whisper without its CPU onnxruntime dependency, with its dependencies explicitly supplied, preventing CPU and GPU wheels from overwriting the same module. Load CUDA libraries before CTranslate2. Dependency-resolution dry runs pass for the combined cutout/transcription stack. These are resolver checks, not proof of live GPU execution.

New requests use a validated UUID job directory within the same runtime. The persistent fixed-code service processes one job at a time, survives ordinary task failures, and retains the current backend model in memory. Switching tasks releases model references to prevent VRAM exhaustion; downloaded model files remain in the session disk cache. Python libraries live in a runtime-local venv inheriting Colab's installed Torch. The service has a heartbeat and exits after 40 idle minutes. This **does not delete the allocated Colab runtime**; users must explicitly end it to stop resource use. Models may be loaded from disk again after switching tools; no claim that all models fit in VRAM is made. Legacy requests remain supported.

Downloader uses the same yt-dlp engine family as the Android LinkDownloads implementation, supports its wider platform allowlist and a supported Node >=22 runtime for EJS challenges. When necessary, a fixed official Node binary is downloaded from nodejs.org and checked against the release SHA-256 list. No challenge scripts are downloaded from arbitrary URLs. Distinct errors identify platform verification, login, DRM, network limits and JS failures. A user-operated Share button can send the URL to installed Android Madar. Cloud IP access can still differ from a phone; no universal download guarantee is possible.

QR now has four orbiting entries: local link/text plus image/media/PDF uploads to the user's Google Drive. Drive uses a separate short-lived drive.file grant in page memory and same-origin fixed API routes. Uploads are capped at 64 MiB; sharing requires explicit public-link consent. Only app-created marked files may be shared by the route. Google Drive API must be enabled in madarfiles; account policies can forbid public-link sharing. This permission flow is implemented but has not been live-tested on the owner's account. Uploaded Drive files persist until the user deletes them or changes sharing.

Arabic name designs have a local canvas tool; generated image names are overlaid using native text rendering instead of asking a diffusion model to draw Arabic glyphs. Chat routes explicit name designs to the local tool. Hero heading uses separate lines; touch/pointer focus no longer permanently pauses the orbit.

Validation includes a real persistent service executing three FFmpeg jobs (success, malformed input, success) with one worker PID, plus namespace/auth/Drive consent/redirect/name-routing regressions. Physical iPhone/Safari behavior and cloud model inference still need live account/device verification.


## 0.8 — independent tool runtimes and closure

Each tool now owns its own Colab runtime, job journal and result checks. Per-tool identifiers live in sessionStorage; the old single localStorage journal is never silently adopted by another tool. Requests carry the exact captured job ID and tool rather than looking up a global current job. The server binds a runtime to a tool marker and refuses cross-tool reads/runs. Shared Google authorization can be reused in the same page, but runtime allocation is independent. Use the same Google account for all tools. Google's concurrent resource limits are dynamic; the UI displays observed counts, not an invented maximum.

Remove the venv/ensurepip bootstrap layer behind PYTHON_ENV_SETUP. Each isolated tool VM uses Colab's existing Python, and starts the reviewed fixed worker directly. The bootstrap regression deliberately makes venv unavailable and still runs. This removes that failing layer; it is not proof of all cloud model inference on the owner's runtime.

The session panel can end individual tool runtimes or all discovered Madar runtimes. On pagehide, a credential-in-body same-origin beacon (keepalive fallback) requests bulk cleanup. The Worker uses waitUntil for background deletion and independent request signals so browser disconnect does not cancel an already accepted cleanup. Only Madar-prefixed runtimes may be deleted. Failed closures remain in the journal; reopening/re-authorizing retries closure rather than reusing a closing session. Google OAuth remains in page memory and is never written to the runtime or persistent browser storage.

A lease is renewed while the page is visible. The tool worker stops after 120 seconds without a page pulse, releasing its process/model memory. This fallback **does not delete the allocated Google VM**. Mobile process kills, offline close, expired authorization or provider errors can prevent VM deletion; the visible Close All button provides a confirmed response before exit. A pagehide beacon cannot be guaranteed by any browser. Keep the page visible during processing. Do not claim unconditional automatic VM termination or zero residual compute charges.

Validation covers per-tool journals, rejected cross-tool status, exact closure target allowlists, partial failure reporting, background cleanup surviving request abort, real worker boot without ensurepip, real FFmpeg jobs surviving malformed input, and expired lease shutdown. Live multi-GPU allocation and physical mobile closure remain unverified.

## 0.9 — result previews, captions and allocation transparency

100 native Arabic name templates (10 structural families), 30 backgrounds and 15 text colors, with local preview and PNG export. Shared result previews cover image/audio/video, PDF pages, text, SRT/VTT and bounded ZIP/DOCX text extraction.

Colab transcription can continue into translation or styled video burn without re-uploading its original media. Follow-ups validate the parent job and source manifest; edited timed text remains data. Groq extracts compatible mono MP3 locally for MKV and oversized supported inputs up to the browser source limit. Translation and Groq transcription can hand timed text to the burn tool.

GPU eligibility checks retain the user's selected accelerator; they never silently select A100. Each allocation displays its requested GPU and safe returned reason. Video exposes approximately 2, 5 and 8 second generation; high-memory is an explicit preferred profile, and standard-memory remains selectable. No promise of Google capacity or live GPU validation.

Session-full policy defaults to asking; optional automatic replacement selects only the oldest completed session with a result present in this page or an errored idle session, never an active operation. One replacement retry uses the same GPU. Restoring metadata after reload clears the local-result flag. Page closure remains best effort. Worker version upgrades refresh fixed task code only while idle.

## 0.10 — distinct frames and runtime recovery

Replace the near-duplicate gallery with 20 independently drawn frames; preserve 30 backgrounds and 15 text colors, place the live canvas above a collapsible compact picker.

Correct the NVENC capability probe from unsupported 64×64 frames to 256×256 YUV420 frames. Identify A100/H100/H200/B200 as having no hardware NVENC, distinguish missing libraries, missing FFmpeg encoder, driver API mismatch and unavailable encoder resources. Hardware encoding remains conditional on a successful real probe; no claim of live GPU validation.

Default video RAM profile to automatic eligibility for the same selected accelerator, preferring standard when eligible. This fixes requesting high-memory L4 when only standard L4 is eligible. RAM shape is separate from GPU VRAM. A100 remains a manual choice.

Use official NLLB safetensors. Bounded retry for transient model transfers. ASR selects a supported CTranslate2 precision, retries a broken VAD without that filter, and uses an official PyTorch Whisper GPU compatibility path for binary/CUDA failures. Sanitized diagnostics contain exception class, fixed-code frames and package versions without user content or provider secrets. Source-manifest-verified retries reuse the uploaded media in the same tool runtime.

Bound heartbeat requests to one in flight per runtime, allow five minutes of missing page pulse before worker exit, cache authenticated runtime connection discovery for 15 seconds keyed by runtime and a SHA-256 token digest, and refresh runtime proxy credentials once without logging out Google authorization. Each tool still owns its runtime. Page-exit allocation deletion remains best effort.

## 0.11 — reproduced NLLB checkpoint failure

Reproduced the actual official 600M checkpoint failure with PyTorch 2.14.1 + Transformers 4.51.3: the safetensors file stores model.decoder.embed_tokens.weight, aliasing model.shared.weight, encoder embeddings and lm_head in metadata. The previous loader failed to restore this mapping and left model.shared.weight on meta. Load the safe state dict, restore its metadata aliases, strict-copy all weights into an allocated model, verify that no meta tensor remains, then transfer to GPU. Never use to_empty or accept random/missing weights. A real CPU run of the full checkpoint translated English to Arabic after repair.

Translation now runs in a fresh, warm child interpreter using the installed dependency stack. It survives parent import contamination, preserves timing and glossary mappings, and reuses its model/PID on the next request. It is released before other GPU models and exits with its owner. ASR installs its complete translation dependencies before ML imports. Runtime worker v6 replaces idle older code without discarding model/download caches or uploaded job sources.

On resumption restore saved cloud options unless the user edited them. A failed ASR→translation retry reuses the completed original SRT when source manifest and language match. Diagnostics include safe missing-import symbols, loaded package versions versus installed versions, and child failures.

Additional QA scripts tests/model_compat_smoke.py and tests/translation_worker_smoke.py require optional PyTorch/Transformers packages; the latter uses cached official NLLB weights and runs in CPU mode only for QA. Production worker CLI still selects CUDA. GPU inference on the owner's Colab account was not available during local QA.

## 0.12 — Wan prompt dependency and platform verification

Wan in diffusers 0.35.1 calls ftfy during prompt preprocessing although it is optional in package metadata. Declare ftfy 6.3.1 explicitly and exercise the installed pipeline prompt cleaner before any model download. Worker v7 refreshes the idle interpreter so optional-import availability flags are rebuilt. Diagnostics retain safe NameError.name and relevant library frames.

Keep the current stable yt-dlp 2026.10.26 + bundled EJS + validated Node runtime. Platform verification is a distinct terminal outcome, not a GPU/dependency failure. Provide opening/sharing the source link from the device without requesting cookies, credentials, proxy services or pretending verification is resolved. No guarantee of platform acceptance; no repeated attempts to evade a verification requirement.

## 0.13 — distinguish completed generation from content review

The reported videogen ValueError at cloud task line 397 is the explicit content-checker rejection after generation completes, not a generator/driver exception. Use CONTENT_REVIEW_REQUIRED with stage metadata and a dedicated review UI rather than TOOL_VALUEERROR. Keep the content checker and thresholds enabled; no rejected frames are exported. Provide editing the prompt, with no automatic regeneration. Evaluate video review with float32 checker weights/inputs and explicit RGB frame batches. Reject incomplete checker output, and report generation, review and export phases separately. Worker v8 refreshes the idle engine.

## 0.14 — explicit family scene conditioning

The reported request “ولد يركض بجانب الشاطيء” is benign. A content-review outcome concerns generated frames and does not establish that the prompt is inappropriate or that the checker is wrong. Retain the action/location and original saved input; for beach child descriptions in Arabic/English, explicitly request a loose long-sleeved shirt, long trousers and sneakers in full framing. Other child scenes request full clothing appropriate to the setting and time period. Add a non-graphic negative conditioning prompt for nudity/exposed torso. Keep the same output review and thresholds, with no automatic regeneration or unchecked delivery. This change cannot guarantee acceptance or establish what the previously blocked frames contained.


## 0.15 — content review diagnostics and checkpoint validation

Repeated review outcomes after a benign stylized scene do not prove prompt misunderstanding or a false positive. Validate complete checker checkpoint loading and reject meta tensors; explicitly use eval mode. Keep every-frame RGB float32 review and original thresholds unchanged. Reject malformed flags instead of interpreting strings/numbers as boolean decisions. Record only the first flagged frame (one-based), timestamp at the actual 16 fps, checked count and total frames; export no rejected images or classification scores. UI no longer implies rewriting a benign prompt is a confirmed fix. No observed output frames or owner GPU access were available to establish the cause of this particular review decision.


## 0.16 — replace the reproduced false-positive video reviewer

Actual CPU inference with the official CompVis checkpoint at cb41f3a270d63d454d385fc2e4f571c487c253c5, Transformers 4.51.3 / diffusers 0.35.1 / torch 2.6.0+cpu reproduced a review false positive: a constant RGB (40,80,120) 512x288 image was flagged individually and in batches of four. The same checker accepted the known cats photograph and official Studio Ghibli still chihiro001.jpg. This establishes a classifier limitation, not the contents or cause of the owner's blocked frame eight.

Video now uses the dedicated binary Falconsai/nsfw_image_detection classifier with pinned revision 96cb0d0342c7afb80cab76ecc58b265fa44da256, safetensors, complete-load validation and float32 inference. This uses the provider's normal/nsfw binary decision at 0.5 (ties blocked), validates label identity and finite logits, scans every frame, and fails closed on load/inference/format failures. The image-generation checker is unchanged. No raw blocked frames, logits or confidence scores are delivered. Diagnostics identify the actual classifier and revision. The 343MB checkpoint caches on the same Colab disk.

Real inference passed cats, Ghibli still, blue, black, white and red references, each single and batched. These safe-reference tests do not establish universal moderation accuracy; unsafe-output decisions additionally have numerical decision-path tests. Optional tests/video_review_smoke.py reproduces the safe regression with downloaded local official checkpoints, without committing weights or copyrighted reference images. Owner L4/CUDA inference and the owner's generated clip were not available for local QA.

Sources: https://huggingface.co/Falconsai/nsfw_image_detection/blob/main/README.md ; https://www.ghibli.jp/works/chihiro/


## 0.17 — product copy and interaction stability

Replace developer-to-owner notes with concise product guidance; retain explicit per-service consent, user account usage, file size caps, temporary result storage and truthful generation limitations. Keep resource choice and allocation diagnostics in closed, optional advanced/support disclosures. Map technical progress/errors to user actions while retaining structured diagnostics for support. Never expose raw exception codes in the primary error UI. Current Site audience is preserved; preparing product copy does not grant public access.

Prevent account/file/consent changes during a Drive upload and ignore late completion after disposal. Isolate each result preview, cancel replaced PDF loading/rendering, serialize page turns and guard stale asynchronous dialog results. These changes cover concrete UI races; they do not certify all provider/GPU/account flows.


## 0.18 — unified captions, layout preview and personal workflow

One visible transcription tool offers transcription, transcription+translation, original-language captions and translated video captions. Audio inputs cannot select video burn. Existing text/SRT and Groq routes remain in optional tools, without duplicate catalog entries. Video jobs upload once, transcribe and optionally translate then compose on the same runtime. Full original/translated/timed text files remain downloadable beside the MP4. Caption preview uses a local frame and sample text, percentage coordinates, normal/bold DejaVu Sans or Amiri, user color and a normalized PNG logo. The exact font files are bundled for browser and FFmpeg; browser and libass shaping/line wrapping can differ slightly. Each frame preview is illustrative, not a promise the sample is actual speech.

Favorites and recent tools, up to five named settings presets per tool, image batches up to ten and supported cloud batches up to five are included. Presets exclude files, text, prompts, names, keys and consent. Inputs and outputs retain explicit memory safeguards. Optional full text artifacts are namespace-bound to the same tool/job. Owner audience remains private; no public sharing or external test accounts were added. Local music removal was not enabled: a stable memory-bounded streaming inference path for large mobile-browser files has not been validated.

Amiri source: google/fonts revision 2e5fa2e951237b6ae65f705693d12ca76a7f78c8 (OFL included). DejaVu fonts retain their license. CPU FFmpeg tests verify burn positions/logo pixels and the four workflow branches with stubbed ASR/translation; owner Colab inference was not available. Browser catalog and operation selection were inspected, but uploading the fixture through the browser automation stalled, so that QA path is incomplete.

## 0.19 — live previews and clear output handling

- Pinned, height-bounded caption and resize previews; the controls scroll beneath them.
- Resize includes adjustable geometric stretch, 0–100%, in portrait, landscape and square. Zero contains with black padding; full strength fills by changing proportions. Preview and FFmpeg use the same size calculation (even pixels). This does not generate new scene content.
- Cloud configs retain a validated original filename across runtime restoration. Results append Arabic processing labels. Browser results also use Arabic suffixes.
- Saved settings now have a compact disclosure, explanation, inline name entry and disabled empty actions; no media or text is saved in presets.
- PDF/image ordering has numbered rows, explicit up/down controls, remove and append actions.
- Tools open a type-specific native picker from the direct user click; browser/OS chooses the final picker surface. Existing select-file controls remain available.
- The video player separates frame-as-JPG capture from timed silent-video export.
- Validation: 83 JavaScript tests and 53 Python tests passed. Real CPU FFmpeg exports cover both resize directions at 0/50/100%. Browser QA exercised PDF selection, reordering, merging and result naming, the presets panel and resize controls. The automation file chooser was slow; owner-account GPU execution and an actual Android picker were not tested in this session.

## 0.20 — compact recent tools and mobile picker categories

Recent tools use a single non-wrapping rail, scroll automatically only when overflowing, allow pointer dragging, and pause for two seconds after interaction. A motion toggle and reduced-motion preference keep it controllable. Re-rendering disposes animation and resize observers.

File chooser hints now convert extension-only lists to MIME types and use image/video/audio family filters for media. PDF requests application/pdf. This covers local, Colab and Drive pickers; native picker appearance remains browser/OS-controlled. Selection checks reject unrelated categories before processing; existing cloud format validation remains in place. Valid file extensions provide fallback when Android omits MIME metadata. No forced camera capture is added.

Validation: 86 JavaScript tests passed; no Python processing changes in this release. Android native picker UI cannot be exercised in the remote desktop browser.

## 0.21 — continuous strip motion and explicit media choices

Recent tools now move using floating-point translate3d coordinates rather than writing scrollLeft and re-reading rounded scroll events. Manual drag retains inertia with frame-rate-independent exponential friction; automatic motion eases back after the two-second touch pause. Layout measurements are cached on resize, and offscreen movement is suspended.

Local, Colab and Drive media inputs now show separate image/video/audio/PDF choices when a tool supports more than one category. Each button requests one MIME category. Native showPicker is preferred, with click fallback. Local selections use fresh input elements and selected-kind checks run before tool handlers. PDF still requests application/pdf, but a website cannot force Android's documents picker to resemble a photo gallery. No guarantee is made about an untested Android native picker.

Validation: 89 JavaScript tests, including separate category filters, native picker fallback and frame-rate-independent subpixel inertia; UI checks verified category choices in local audio, Colab separation and conversion tools. Android motion/picker behavior requires device verification.

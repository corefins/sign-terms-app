# ERPDocs Embedded Signing — Client Integration Guide

This document describes the ERPDocs SignPack API integration implemented in this
application (`sign_terms_app.py`). Hand this to the client's engineering team.

---

## 1. What the integration does

1. Client collects company details + signature consent in their own UI.
2. Client backend generates a PDF with an **anchor tag** where the signature goes.
3. Client backend creates a **SignPack** on ERPDocs, mints a short-lived
   **embed token**, and embeds the returned `sign_url` in an `<iframe>`.
4. Signer signs inside the iframe (email OTP verification + drawn/typed signature).
5. Client backend polls the SignPack status, then downloads the **signed PDF +
   completion certificate** via API.

---

## 2. Credentials & settings the client must have

| Setting | Where it goes | Notes |
|---|---|---|
| `erpdocs_base_url` | Server config / secrets | `https://www.erpdocs.com/api/v1` |
| `erpdocs_api_key` | Server config / secrets | **Live key** — sandbox keys are rejected by the embed-token endpoint |
| `erpdocs_sender_email` | Server config / secrets | Must be an **active user in the ERPDocs organization** |
| `signpack_origin` | Server config / secrets | Exact origin of the page hosting the iframe, e.g. `https://appsigning.streamlit.app` (scheme + host, **no path, no trailing slash**) |

### One-time ERPDocs admin setup (on the client's ERPDocs account)

1. Create an **API key** with scopes: `signpack.write`, `signpack.embed`, `signpack.read`.
2. Register the **frame origin** under *Admin → API & Webhooks* — must exactly match
   `signpack_origin` (e.g. `https://appsigning.streamlit.app`, not `http://`, no `/`).
3. Set verification floor to `email_otp`.
4. Ensure SMTP is configured on ERPDocs so OTP emails are delivered.

---

## 3. API calls implemented

All calls are **server-to-server** — the API key must never reach the browser.

### 3.1 Create + send SignPack

```http
POST {base}/signpacks
Authorization: Bearer <live_key>
Content-Type: multipart/form-data
```

| Field | Value |
|---|---|
| `file` | The generated PDF (contains `{{sig:signer 1}}` anchor text) |
| `sender_email` | Active org user email |
| `title` | e.g. `Agreement - <Company>` |
| `send` | `true` |
| `recipients` | JSON: `{"signer 1": {"name": "...", "email": "...", "embedded": true}}` |

**Anchor tag:** the PDF must contain literal text `{{sig:signer 1}}` where the
signature field should appear. The recipient role key (`signer 1`) must match the
anchor name **case-insensitively**. ERPDocs strips the text and places a real
signature field there.

Response (key fields): `signpack_id` / `id`, and `recipients` (dict keyed by role
or list) each with an `id`.

### 3.2 Mint embed token

```http
POST {base}/signpacks/{signpack_id}/recipients/{recipient_id}/embed-token
Authorization: Bearer <live_key>
Content-Type: application/json
```

```json
{
  "origin": "https://appsigning.streamlit.app",
  "redirect_url": "https://appsigning.streamlit.app?signpack_download=1",
  "require_verification": "email_otp",
  "ttl_seconds": 900,
  "signer_authenticated": {
    "method": "host_account",
    "identifier": "<client's logged-in user id/email>",
    "authenticated_at": "<ISO-8601 timestamp>"
  },
  "suppress_completion_email": true
}
```

Returns `{"sign_url": "https://..."}` — **single-use, ≤900 s TTL**. Mint a fresh
token immediately before rendering the iframe; if the user revisits, mint again.

### 3.3 Embed (browser)

```html
<iframe src="<sign_url>"
        style="width:100%; height:780px; border:none;"
        sandbox="allow-scripts allow-same-origin allow-popups allow-forms">
</iframe>
```

### 3.4 Poll status

```http
GET {base}/signpacks/{signpack_id}
Authorization: Bearer <live_key>
```

Poll every ~5–6 s until `status` is `completed` / `signed` (match
case-insensitively). Treat webhooks — not browser events — as authoritative.

### 3.5 Download signed document

```http
GET {base}/signpacks/{signpack_id}/download
Authorization: Bearer <live_key>
```

Response is **JSON metadata**, not the file itself:

```json
{
  "documents": [{
    "filename": "Agreement - X_signed.pdf",
    "pades_valid": true,
    "sha256": "…",
    "url": "https://…s3…/signed_final.pdf?X-Amz-…"
  }],
  "signpack_id": 623,
  "status": "Completed"
}
```

Fetch `documents[0].url` to get the PDF bytes.

> **Critical:** if `url` is a **presigned S3 URL** (contains `X-Amz-`), fetch it
> with **no extra headers** — sending the `Authorization` header makes AWS
> reject the request. Only attach the API key for URLs on the ERPDocs domain.
> Verify the downloaded bytes start with `%PDF` before saving/serving.

---

## 4. Reference flow (as implemented in `sign_terms_app.py`)

```
form submit → build PDF with {{sig:signer 1}} anchor
            → POST /signpacks                 (save signpack_id, recipient_id)
            → POST …/embed-token              (fresh token per page load)
            → <iframe src=sign_url>           (signer: OTP → sign → submit)
            → GET /signpacks/{id} poll 6s     (until status = completed)
            → GET /signpacks/{id}/download    (JSON → follow url → PDF bytes)
            → present download to user
```

---

## 5. Gotchas observed during integration

- **`sender_not_found`** → `sender_email` must be an active org user.
- **`origin_not_allowed`** → register the exact origin (scheme + host, no slash)
  in ERPDocs Admin before minting tokens.
- **iframe CSP `frame-ancestors 'none'`** → the origin must be allow-listed on the
  live ERPDocs org, not just on a local/test instance.
- **Browser `postMessage`/redirects are not authoritative** — completion must be
  confirmed via status polling or webhooks.
- **Never** pass the API key to the browser or call these endpoints from frontend JS.
- Store `signpack_id` in your DB so signed documents can be re-downloaded later.

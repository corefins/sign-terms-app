"""Sign the Term — demo onboarding app.

A standalone Streamlit app (separate from client_email_app.py) with a demo
left menu. The "Sign the Term" page collects basic company information,
shows the terms & conditions, requires an explicit agreement checkbox and a
signature, then generates a downloadable PDF of the signed agreement.

Run:
    .venv/bin/streamlit run sign_terms_app.py --server.port 8502
"""
from __future__ import annotations

import html
import json
from pathlib import Path
 
import requests
import io
from datetime import datetime, timezone

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Page config ─────────────────────────────────────────────────────────────
def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
 
ROOT = Path(__file__).resolve().parent
_file_secrets = _load_json(ROOT / "secrets.json")


def _secret(key: str, default: str = "") -> str:
    # On Streamlit Cloud, credentials come from st.secrets (App settings →
    # Secrets). Locally we fall back to secrets.json.
    try:
        val = st.secrets.get(key)
        if val:
            return str(val)
    except Exception:
        pass
    return _file_secrets.get(key, default)


ERPDOCS_BASE_URL = (_secret("erpdocs_base_url") or "http://localhost:5000/api/v1").rstrip("/")
ERPDOCS_API_KEY = _secret("erpdocs_api_key")
ERPDOCS_SENDER_EMAIL = _secret("erpdocs_sender_email")
SIGNPACK_ORIGIN = (_secret("signpack_origin") or "http://localhost:8502").rstrip("/")


st.set_page_config(
    page_title="Ikiru — Partner Onboarding",
    page_icon="📝",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.5rem !important; max-width: 1100px; }
      .st-hero {
        background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
        border-radius: 16px; padding: 28px 32px; margin-bottom: 24px;
        color: #f1f5f9;
      }
      .st-hero h1 { font-size: 1.5rem; font-weight: 700; margin: 0 0 6px 0; color: #fff; }
      .st-hero p { font-size: .88rem; color: #cbd5e1; margin: 0; }
      .st-card {
        background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
        padding: 24px 28px; margin-bottom: 18px;
        box-shadow: 0 1px 3px rgba(0,0,0,.06);
      }
      .st-card h3 { margin: 0 0 14px 0; font-size: 1.05rem; color: #1e293b; }
      .st-terms {
        background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
        padding: 18px 22px; max-height: 340px; overflow-y: auto;
        font-size: .84rem; color: #334155; line-height: 1.65;
      }
      .st-terms h4 { margin: 14px 0 4px 0; font-size: .9rem; color: #1e293b; }
      .st-terms p { margin: 0 0 8px 0; }
      .st-signed {
        background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 10px;
        padding: 16px 20px; margin-bottom: 18px; font-size: .9rem; color: #15803d;
      }
      .st-demo {
        background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 10px;
        padding: 20px 24px; font-size: .9rem; color: #075985;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Terms & conditions content ──────────────────────────────────────────────
TERMS = [
    ("1. Engagement & Scope", [
        "The Company engages the Service Provider for accounting automation, data processing, "
        "and related professional services as described in the applicable statement of work.",
        "Any work outside the agreed scope requires a written change request approved by both parties.",
        "The Service Provider may update its tools and workflows, provided the delivered service "
        "levels are not reduced.",
    ]),
    ("2. Client Responsibilities", [
        "The Company shall provide accurate, complete, and timely information, documents, and "
        "access required to perform the services.",
        "The Company is responsible for the legality and authenticity of all data it supplies.",
        "Delays caused by missing or incorrect information may extend delivery timelines without "
        "liability to the Service Provider.",
    ]),
    ("3. Data & Confidentiality", [
        "Both parties shall keep all non-public information strictly confidential and use it only "
        "for the purpose of this engagement.",
        "Financial data, credentials, and business records shall be handled with reasonable "
        "industry-standard security controls.",
        "Confidentiality obligations survive the termination of this agreement for a period of "
        "three (3) years.",
    ]),
    ("4. Data Processing & Storage", [
        "The Company consents to the processing and storage of its data on systems operated by "
        "the Service Provider and its sub-processors.",
        "Data may be retained for statutory record-keeping periods even after the engagement ends.",
        "The Company may request export or deletion of its data, subject to legal retention "
        "requirements.",
    ]),
    ("5. Fees & Payment", [
        "Fees are charged as per the agreed commercial schedule and are exclusive of applicable taxes.",
        "Invoices are payable within fifteen (15) days of issue unless otherwise agreed in writing.",
        "Late payments may attract interest at 1.5% per month or the maximum permitted by law, "
        "whichever is lower.",
    ]),
    ("6. Intellectual Property", [
        "All tools, templates, scripts, and automation frameworks developed or used by the Service "
        "Provider remain its exclusive property.",
        "The Company receives a non-exclusive, non-transferable right to use deliverables for its "
        "internal business purposes.",
        "Reports and outputs generated from the Company's data belong to the Company.",
    ]),
    ("7. Warranties & Liability", [
        "Services are provided with reasonable skill and care but without any guarantee of "
        "error-free outcomes.",
        "The Service Provider is not liable for indirect, incidental, or consequential losses, "
        "including loss of profit or data.",
        "Total aggregate liability shall not exceed the fees paid in the three (3) months "
        "preceding the claim.",
    ]),
    ("8. Compliance & Filings", [
        "Statutory filings and submissions remain the legal responsibility of the Company unless "
        "expressly delegated in writing.",
        "The Company shall review and approve all filings before submission deadlines.",
        "Penalties arising from incorrect data supplied by the Company are the Company's "
        "responsibility.",
    ]),
    ("9. Term & Termination", [
        "This agreement remains in effect until terminated by either party with thirty (30) days "
        "written notice.",
        "Either party may terminate immediately for material breach that is not cured within "
        "fourteen (14) days of notice.",
        "Upon termination, all outstanding fees become immediately payable.",
    ]),
    ("10. General", [
        "This agreement is governed by the laws applicable at the Service Provider's principal "
        "place of business.",
        "If any provision is held invalid, the remaining provisions continue in full force.",
        "This document, together with referenced schedules, constitutes the entire agreement "
        "between the parties.",
    ]),
]


def _terms_html() -> str:
    parts = []
    for heading, paras in TERMS:
        parts.append(f"<h4>{heading}</h4>")
        for p in paras:
            parts.append(f"<p>{p}</p>")
    return "".join(parts)


# ── PDF generation ──────────────────────────────────────────────────────────
def build_agreement_pdf(form: dict, signer: str, designation: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="Signed Terms & Conditions",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=18, spaceAfter=4)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9,
                         textColor=colors.HexColor("#64748b"), spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=styles["Heading4"], fontSize=10.5,
                        spaceBefore=10, spaceAfter=3)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9,
                          leading=13, spaceAfter=4)
    label = ParagraphStyle("label", parent=body, textColor=colors.HexColor("#64748b"))

    signed_at = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")

    story = [
        Paragraph("Terms &amp; Conditions — Signed Agreement", h1),
        Paragraph(f"Signed electronically on {signed_at}", sub),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")),
        Spacer(1, 8),
        Paragraph("Terms &amp; Conditions", h2),
    ]

    for heading, paras in TERMS:
        story.append(Paragraph(heading, h2))
        for p in paras:
            story.append(Paragraph(p, body))

    rows = [[Paragraph("Field", label), Paragraph("Details", label)]]
    for k, v in form.items():
        rows.append([Paragraph(k, body), Paragraph(v or "—", body)])
    table = Table(rows, colWidths=[55 * mm, 115 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [Spacer(1, 10), HRFlowable(width="100%", thickness=1,
              color=colors.HexColor("#e2e8f0")),
              Paragraph("Company Information", h2), table]

    story += [
        Spacer(1, 14),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")),
        Spacer(1, 8),
        Paragraph("Signature", h2),
        Paragraph(f"Signed by: <b>{signer}</b> ({designation})", body),
        Paragraph(f"Company: {form.get('Company Name', '—')}", body),
        Paragraph(f"Signed-in account: {form.get('Signed-in Account', '—')}", body),
        Paragraph(f"Date: {signed_at}", body),
        Spacer(1, 20),
        Paragraph("{{sig:signer 1}}", ParagraphStyle(
    "sig", parent=body, fontSize=16, textColor=colors.lightgrey)),
    ]

    doc.build(story)
    return buf.getvalue()


# ── Pages ───────────────────────────────────────────────────────────────────
def _api_headers() -> dict:
    return {"Authorization": f"Bearer {ERPDOCS_API_KEY}"}


def _create_signpack(pdf_bytes: bytes, company: str, signer_email: str, signer_name: str) -> dict | None:
    files = {"file": ("agreement.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {
        "sender_email": ERPDOCS_SENDER_EMAIL or "deepak@corefins.com",
        "title": f"Agreement - {company}",
        "send": "true",
        "recipients": json.dumps({
            "signer 1": {
                "name": signer_name,
                "email": signer_email,
                "embedded": True,
            }
        }),
    }
    r = requests.post(f"{ERPDOCS_BASE_URL}/signpacks",
                      headers=_api_headers(), files=files, data=data)
    if not r.ok:
        st.error(f"SignPack creation failed: {r.status_code} - {r.text[:1000]}")
        return None
    try:
        return r.json()
    except requests.exceptions.JSONDecodeError:
        st.error(
            f"SignPack creation returned non-JSON. Status: {r.status_code}, "
            f"Content-Type: {r.headers.get('Content-Type', 'unknown')}, "
            f"body: {r.text[:1000]}"
        )
        return None


def _get_embed_token(signpack_id: str, recipient_id: str) -> str | None:
    payload = {
        "origin": SIGNPACK_ORIGIN,
        "redirect_url": f"{SIGNPACK_ORIGIN}?signpack_download=1",
        "require_verification": "email_otp",
        "ttl_seconds": 900,
        "signer_authenticated": {
            "method": "host_account",
            "identifier": st.session_state.get("user_email", "anonymous"),
            "authenticated_at": datetime.now(timezone.utc).isoformat(),
        },
        "suppress_completion_email": True,
    }
    r = requests.post(
        f"{ERPDOCS_BASE_URL}/signpacks/{signpack_id}/recipients/{recipient_id}/embed-token",
        headers={**_api_headers(), "Content-Type": "application/json"},
        json=payload,
    )
    if not r.ok:
        st.error(f"Embed token failed: {r.status_code} - {r.text}")
        return None
    return r.json()["sign_url"]

def _render_signed_download(signpack_id: str, company_slug: str = "signed") -> None:
    r = requests.get(
        f"{ERPDOCS_BASE_URL}/signpacks/{signpack_id}",
        headers=_api_headers(),
    )
    status = str(r.json().get("status", "")).lower() if r.ok else None
    if status not in _DONE_STATUSES:
        st.warning(f"Status: {status or 'unknown'}. The document is still being processed.")
        if st.button("Check again"):
            st.rerun()
        return

    r = requests.get(
        f"{ERPDOCS_BASE_URL}/signpacks/{signpack_id}/download",
        headers=_api_headers(),
        timeout=30,
    )
    pdf_bytes = b""
    filename = f"agreement_{company_slug}_signed.pdf"

    if r.ok and r.content.startswith(b"%PDF"):
        pdf_bytes = r.content
    elif r.ok and "json" in r.headers.get("Content-Type", ""):
        try:
            doc = r.json()["documents"][0]
        except (KeyError, IndexError, ValueError):
            st.error(f"Unexpected download response: {r.text[:500]}")
            return
        url = doc.get("url") or ""
        filename = doc.get("filename") or filename
        site_root = ERPDOCS_BASE_URL.split("/api")[0].rstrip("/")
        candidates = [url]
        if url.startswith("/"):
            candidates.insert(0, site_root + url)
        for cand in candidates:
            if cand.startswith("http"):
                # Presigned URLs (e.g. S3 X-Amz-*) reject extra auth headers —
                # fetch them bare; only send the API key for ERPDocs URLs.
                use_auth = "X-Amz-" not in cand and site_root in cand
                fr = requests.get(
                    cand,
                    headers=_api_headers() if use_auth else {},
                    timeout=30,
                )
                if fr.ok and fr.content.startswith(b"%PDF"):
                    pdf_bytes = fr.content
                    break
            elif Path(cand).exists():
                pdf_bytes = Path(cand).read_bytes()
                break
        if not pdf_bytes:
            st.error(f"Signed file not reachable. url={url} tried={candidates}")
            return
    else:
        st.error(
            f"Download did not return a PDF. Status: {r.status_code}, "
            f"Content-Type: {r.headers.get('Content-Type', '')}, "
            f"size: {len(r.content)} bytes."
        )
        st.code(r.text[:1000])
        return

    if not pdf_bytes.startswith(b"%PDF"):
        st.error(f"Fetched file is not a PDF ({len(pdf_bytes)} bytes).")
        return

    st.markdown(
        '<div class="st-signed"><b>Agreement signed.</b> '
        "Download your signed copy below.</div>",
        unsafe_allow_html=True,
    )
    st.download_button(
        "⬇ Download signed agreement",
        data=pdf_bytes,
        file_name=filename,
        mime="application/pdf",
        type="primary",
    )


_DONE_STATUSES = {"completed", "signed", "complete", "done"}


@st.fragment(run_every="6s")
def _poll_signpack_status(signpack_id: str) -> None:
    try:
        r = requests.get(
            f"{ERPDOCS_BASE_URL}/signpacks/{signpack_id}",
            headers=_api_headers(),
            timeout=10,
        )
        status = str(r.json().get("status", "")).lower() if r.ok else f"HTTP {r.status_code}"
    except Exception as exc:
        status = f"error: {exc}"
    st.caption(f"Auto-checking signing status… **{status}**")
    if status in _DONE_STATUSES:
        st.session_state.pop("sign_url", None)
        st.session_state["signpack_done"] = True
        st.rerun(scope="app")


def page_sign_terms() -> None:
    if "signpack_download" in st.query_params and "signpack_id" in st.session_state:
        _render_signed_download(st.session_state["signpack_id"], st.session_state.get("signpack_company", "signed"))
        if st.button("Start a new agreement"):
            for k in ("signpack_done", "signpack_id", "signpack_company",
                      "signpack_email", "signpack_recipient_id", "sign_url"):
                st.session_state.pop(k, None)
            st.query_params.clear()
            st.rerun()
        return

    if "sign_url" in st.session_state:
        signpack_id = st.session_state["signpack_id"]
        recipient_id = st.session_state.get("signpack_recipient_id")

        # Mint a fresh embed token each time so the iframe never shows "session ended"
        if recipient_id:
            new_url = _get_embed_token(signpack_id, recipient_id)
            if new_url:
                st.session_state["sign_url"] = new_url

        st.markdown(
            '<div class="st-hero"><h1>Sign the Term</h1>'
            "<p>Sign inside the embedded window below.</p></div>",
            unsafe_allow_html=True,
        )
        st.caption(
            f"Signature is associated with **{st.session_state.get('signpack_email', '—')}** "
            f"— check that inbox for the verification code."
        )
        if st.button("🔄 I've signed — get the signed document"):
            r = requests.get(
                f"{ERPDOCS_BASE_URL}/signpacks/{signpack_id}",
                headers=_api_headers(),
            )
            status = str(r.json().get("status", "")).lower() if r.ok else None
            if status in _DONE_STATUSES:
                st.session_state["signpack_done"] = True
                st.session_state.pop("sign_url", None)
                st.rerun()
            else:
                st.info(f"Current status: {status or 'unknown'}. Sign in the window below, then check again.")

        st.link_button(
            "📱 Signing on mobile? Open the signing page in a new tab",
            st.session_state["sign_url"],
            help="Recommended on phones — switching apps reloads the iframe.",
        )

        st.markdown('<div style="border-radius:12px; overflow:hidden; border:1px solid #e2e8f0;">', unsafe_allow_html=True)
        st.components.v1.html(
            f'<iframe src="{html.escape(st.session_state["sign_url"])}" '
            'style="width:100%; height:780px; border:none;" allow="camera; fullscreen" '
            'sandbox="allow-scripts allow-same-origin allow-popups allow-forms"></iframe>',
            height=780,
            scrolling=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)

        _poll_signpack_status(signpack_id)
        return

    if st.session_state.get("signpack_done"):
        _render_signed_download(st.session_state["signpack_id"], st.session_state.get("signpack_company", "signed"))
        if st.button("Start a new agreement"):
            for k in ("signpack_done", "signpack_id", "signpack_company",
                      "signpack_email", "signpack_recipient_id", "sign_url"):
                st.session_state.pop(k, None)
            st.rerun()
        return

    st.markdown(
        '<div class="st-hero"><h1>Sign the Term</h1>'
        "<p>Fill in your company details, review the terms &amp; conditions, "
        "and sign to receive a PDF copy of the agreement.</p></div>",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="st-card"><h3>Company Information</h3>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        company = st.text_input("Company Name *")
        gstin = st.text_input("GSTIN")
        pan = st.text_input("PAN")
    with c2:
        contact = st.text_input("Contact Person *")
        email = st.text_input("Email *", value=st.session_state.get("user_email", ""))
        phone = st.text_input("Phone")
    address = st.text_area("Registered Address", height=80)
    s1, s2 = st.columns(2)
    with s1:
        signer = st.text_input("Full name of authorised signatory *")
    with s2:
        designation = st.text_input("Designation", placeholder="e.g. Director, Partner")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="st-card"><h3>Terms &amp; Conditions</h3>', unsafe_allow_html=True)
    st.markdown(f'<div class="st-terms">{_terms_html()}</div>', unsafe_allow_html=True)
    st.caption(
        f"The signing request and verification code will be sent to "
        f"**{email.strip() or st.session_state.get('user_email', '—')}** "
        f"(the Email field above)."
    )
    agree = st.checkbox(
        "I have read and agree to the terms & conditions above. I am authorised "
        "to sign on behalf of the company."
    )
    if st.button("✍️ Sign & Generate PDF", type="primary", disabled=not agree):
        missing = [name for name, val in
                   [("Company Name", company), ("Contact Person", contact),
                    ("Email", email), ("Signatory name", signer)] if not val.strip()]
        if missing:
            st.error("Please fill required fields: " + ", ".join(missing))
        else:
            form = {
                "Company Name": company.strip(),
                "GSTIN": gstin.strip(),
                "PAN": pan.strip(),
                "Contact Person": contact.strip(),
                "Email": email.strip(),
                "Phone": phone.strip(),
                "Registered Address": address.strip(),
                "Authorised Signatory": signer.strip(),
                "Designation": designation.strip() or "Authorised Signatory",
                "Signed-in Account": st.session_state.get("user_email", "—"),
            }
            pdf = build_agreement_pdf(form, signer.strip(),
                                      designation.strip() or "Authorised Signatory")

            result = _create_signpack(pdf, company.strip(), email.strip(), signer.strip())
            if not result:
                st.stop()

            signpack_id = result.get("id") or result.get("signpack_id") \
                or (result.get("signpack") or {}).get("id")
            recipients = result.get("recipients") or (result.get("signpack") or {}).get("recipients") or {}
            if isinstance(recipients, list):
                recipient_id = recipients[0].get("id") if recipients else None
            else:
                recipient_id = (recipients.get("signer 1") or recipients.get("Signer 1") or {}).get("id")

            if not signpack_id or not recipient_id:
                st.error(f"Could not parse SignPack response: {result}")
                st.stop()

            st.session_state["signpack_recipient_id"] = recipient_id

            sign_url = _get_embed_token(signpack_id, recipient_id)
            if not sign_url:
                st.stop()

            st.session_state["signpack_id"] = signpack_id
            st.session_state["signpack_company"] = company.strip().replace(" ", "_")
            st.session_state["signpack_email"] = email.strip()
            st.session_state["sign_url"] = sign_url
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def page_demo(title: str) -> None:
    st.markdown(
        f'<div class="st-hero"><h1>{title}</h1>'
        "<p>Demo page — content coming soon.</p></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="st-demo">This is a placeholder menu item. '
        "Select <b>Sign the Term</b> from the left menu for the working flow.</div>",
        unsafe_allow_html=True,
    )


# ── Login gate ──────────────────────────────────────────────────────────────
def page_login() -> None:
    st.markdown(
        '<div class="st-hero"><h1>Welcome</h1>'
        "<p>Sign in to access the onboarding portal.</p></div>",
        unsafe_allow_html=True,
    )
    st.markdown('<div class="st-card"><h3>Sign In</h3>', unsafe_allow_html=True)
    login_email = st.text_input("Email ID *", key="login_email")
    if st.button("Sign In", type="primary"):
        if not login_email.strip() or "@" not in login_email:
            st.error("Please enter a valid email ID.")
        else:
            # Demo auth — the email is kept in session_state for the
            # lifetime of this session.
            st.session_state["user_email"] = login_email.strip()
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


if "user_email" not in st.session_state:
    page_login()
    st.stop()

# ── Left menu ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🧭 Menu")
    menu = st.radio(
        "Navigate",
        ["Dashboard", "Clients", "Documents", "Sign the Term", "Reports", "Settings"],
        index=3,
        label_visibility="collapsed",
    )
    st.caption(f"Signed in as {st.session_state['user_email']}")
    if st.button("Sign out"):
        for k in ("user_email", "signed_pdf", "sign_url", "signpack_id",
                  "signpack_done", "signpack_company", "signpack_email",
                  "signpack_recipient_id"):
            st.session_state.pop(k, None)
        st.rerun()

if menu == "Sign the Term":
    page_sign_terms()
else:
    page_demo(menu)

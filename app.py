"""
PDF → EDI Converter
Scans any vendor PDF invoice and generates a fixed-width EDI file.
Format: A (header), B (line items), C (taxes/fees)
"""

import streamlit as st
import pdfplumber
import re
import io
import zipfile
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ── Optional: OCR ─────────────────────────────────────────────────────────────
try:
    from pdf2image import convert_from_bytes
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class LineItem:
    description: str = ""
    upc: str = ""
    item_code: str = ""
    cases: int = 0
    quantity: int = 0
    unit_price: float = 0.0
    net_amount: float = 0.0


@dataclass
class Invoice:
    vendor: str = ""
    vendor_code: str = ""
    invoice_number: str = ""
    date: Optional[datetime] = None
    items: list = field(default_factory=list)
    taxes: float = 0.0
    total: float = 0.0
    raw_text: str = ""
    parse_method: str = ""


# ══════════════════════════════════════════════════════════════════════════════
# TEXT EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_text_pdfplumber(pdf_bytes: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
            return "\n".join(pages).strip()
    except Exception:
        return ""


def extract_text_ocr(pdf_bytes: bytes) -> str:
    if not OCR_AVAILABLE:
        return ""
    try:
        images = convert_from_bytes(pdf_bytes, dpi=300)
        return "\n".join(
            pytesseract.image_to_string(img, config="--psm 6") for img in images
        ).strip()
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# UNIVERSAL INVOICE PARSER
# ══════════════════════════════════════════════════════════════════════════════

# Lines that look like company names
_COMPANY_RE = re.compile(
    r"\b(INC\.?|LLC|CORP\.?|LTD\.?|CO\b|SERVICES?\b|DISTRIBUT\w+|BEVERAG\w+|SUPPLY\b|GROUP\b|COMPANY\b)",
    re.IGNORECASE,
)

# Lines to skip when looking for item descriptions
_SKIP_LINE = re.compile(
    r"^\s*(DESCRIPTION|ITEM\b|PRODUCT|QTY\b|QUANTITY|UNIT\b|PRICE|EXT\b|EXTENDED|"
    r"AMOUNT|TOTAL|SUBTOTAL|SUB\s*TOTAL|TAX|INVOICE|DATE|PAGE|DUE|BALANCE|"
    r"DISCOUNT|FREIGHT|SHIPPING|HANDLING|TERMS|SHIP\s*TO|BILL\s*TO|SOLD\s*TO|"
    r"PHONE|FAX|WWW|HTTP|@|THANK|PLEASE|REMIT|NOTES?|COMMENTS?)",
    re.IGNORECASE,
)

# Descriptions that are actually totals/subtotals
_DESC_SKIP = re.compile(
    r"\b(TOTAL|SUBTOTAL|SUB\s*TOTAL|AMOUNT\s*DUE|BALANCE)\b", re.IGNORECASE
)


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _i(v) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def parse_invoice(text: str) -> Invoice:
    inv = Invoice(parse_method="pdfplumber+regex")

    # Vendor: first line that looks like a company name
    for line in text.split("\n"):
        line = line.strip()
        if len(line) > 3 and _COMPANY_RE.search(line):
            inv.vendor = line[:40]
            inv.vendor_code = re.sub(r"[^A-Z0-9]", "", line.upper())[:6] or "GNRC"
            break

    # Invoice number (must start with a digit to avoid matching words)
    for pat in [
        r"REPRINT/(\d+)/",
        r"(?:INVOICE|INV)\s*(?:NO\.?|NUM\.?|NUMBER|#|:)?\s*(\d[\d\-/]{2,})",
        r"(?<!\w)#\s*(\d{4,})",
        r"(?:ORDER|PO)\s*(?:NO\.?|#)?\s*(\d[\d\-]{3,})",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            inv.invoice_number = m.group(1)
            break

    # Date
    for pat, fmt in [
        (r"\b(\d{1,2}/\d{1,2}/\d{4})\b", "%m/%d/%Y"),
        (r"\b(\d{1,2}/\d{1,2}/\d{2})\b",  "%m/%d/%y"),
        (r"\b(\d{4}-\d{2}-\d{2})\b",       "%Y-%m-%d"),
    ]:
        m = re.search(pat, text)
        if m:
            try:
                inv.date = datetime.strptime(m.group(1), fmt)
                break
            except ValueError:
                pass

    # Taxes (space before capture prevents greedy backtracking from eating digits)
    for tm in re.finditer(
        r"(?:TAX(?:ES)?|EXCISE|SURCHARGE|DEPOSIT)[^\n]* ([\d,]+\.\d{2})-?",
        text, re.IGNORECASE,
    ):
        inv.taxes += _f(tm.group(1).replace(",", ""))

    # Total
    for kw in [r"AMOUNT\s*DUE", r"BALANCE\s*DUE", r"TOTAL\s*DUE", r"GRAND\s*TOTAL", r"TOTAL"]:
        m = re.search(kw + r"[\s:$]*([\d,]+\.\d{2})-?", text, re.IGNORECASE)
        if m:
            inv.total = _f(m.group(1).replace(",", ""))
            break

    inv.items = _extract_line_items(text)

    if not inv.total and inv.items:
        inv.total = sum(i.net_amount for i in inv.items) + inv.taxes

    return inv


def _extract_line_items(text: str) -> list:
    """
    Pass 1 — structured fixed-column rows (item_code  qty  description  ...  net)
             Handles distributor formats like J. Polep. If it finds items, Pass 2 is skipped.
    Pass 2 — amount-ending lines (any line whose last token is a dollar amount).
             Handles standard invoice layouts.
    """
    items = []
    seen = set()

    def _add(desc, net, item_code="", upc="", cases=0, qty=0, unit_price=0.0):
        desc = desc.strip()[:25]
        if not desc or len(desc) < 3 or not re.search(r"[A-Za-z]", desc) or _DESC_SKIP.search(desc):
            return
        key = (desc[:20].lower(), round(net, 2))
        if key in seen:
            return
        seen.add(key)
        items.append(LineItem(
            description=desc, item_code=item_code, upc=upc,
            cases=cases, quantity=qty or cases,
            unit_price=unit_price, net_amount=net,
        ))

    # Pass 1: leading item-code, qty, description, 2-10 numeric columns, net amount
    for m in re.finditer(
        r"^(\d{4,8})\s+(\d+)-?\s+(.+?)\s+(?:[\d.]+\s+){2,10}([\d,]+\.\d{2})-?\s*$",
        text, re.MULTILINE,
    ):
        net = _f(m.group(4).replace(",", ""))
        desc = m.group(3).strip()
        if net > 0 and not _DESC_SKIP.search(desc):
            _add(desc, net, item_code=m.group(1), cases=_i(m.group(2)))

    if items:
        return items

    # Pass 2: lines ending with a dollar amount
    for line in text.split("\n"):
        line = line.strip()
        if not line or len(line) < 6 or _SKIP_LINE.match(line):
            continue
        m = re.search(r"\$?\s*([\d,]+\.\d{2})\s*$", line)
        if not m:
            continue
        net = _f(m.group(1).replace(",", ""))
        if net <= 0:
            continue
        desc = line[: m.start()].strip()
        desc = re.sub(r"^[\dA-Z#\-]{1,12}\s+", "", desc).strip()
        desc = re.sub(r"(\s+[\d,]+\.?\d*){1,3}\s*$", "", desc).strip()
        _add(desc, net)

    return items


# ══════════════════════════════════════════════════════════════════════════════
# EDI GENERATOR
# Format: A{vendor:9}{invoice:7}{MMDDYY:6}{amt:10}
#         B{code:6}{qty:5}{desc:25}{upc:12}  {seq:6}{amt:13}
#         C{desc:28}{amt:9}
# Amounts: sign ('-') + zero-padded cents, no decimal point
# ══════════════════════════════════════════════════════════════════════════════

def _edi_amount(value: float, width: int) -> str:
    cents = round(abs(value) * 100)
    return f"-{str(cents).zfill(width - 1)[-(width - 1):]}"


def invoice_to_edi(inv: Invoice) -> str:
    lines = []
    raw_inv = re.sub(r"\D", "", inv.invoice_number or "0")
    inv_num = raw_inv[-7:].zfill(7) if raw_inv else "0000000"
    date_str = inv.date.strftime("%m%d%y") if inv.date else datetime.now().strftime("%m%d%y")
    vendor = (inv.vendor_code or "GNRC").upper()[:9].ljust(9)
    total = inv.total or sum(i.net_amount for i in inv.items)

    lines.append(f"A{vendor}{inv_num}{date_str}{_edi_amount(total, 10)}")

    for seq, item in enumerate(inv.items, start=1):
        upc_clean = re.sub(r"\D", "", item.upc or "")
        code = upc_clean[:6] if upc_clean else (item.item_code or "").ljust(6)[:6] or "000000"
        qty = str(max(item.cases, item.quantity, 0)).zfill(5)[:5]
        lines.append(
            f"B{code}{qty}{item.description[:25].ljust(25)}"
            f"{upc_clean[:12].ljust(12)}  {str(seq).zfill(6)}{_edi_amount(item.net_amount, 13)}"
        )

    if inv.taxes > 0:
        lines.append(f"C{'TAXES AND FEES FOR A INVOICE'[:28].ljust(28)}{_edi_amount(inv.taxes, 9)}")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# PROCESSING PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def _edi_filename(inv: Invoice, source_filename: str) -> str:
    raw_num = re.sub(r"\D", "", inv.invoice_number or "")
    if raw_num:
        return f"S{raw_num[-7:].zfill(7)}.TXT"
    stem = Path(source_filename).stem[:7].upper().replace(" ", "")
    return f"S{stem}.TXT"


def _unique(name: str, seen: set) -> str:
    """Return name unchanged if not seen, else append _2, _3, ... until unique."""
    if name not in seen:
        seen.add(name)
        return name
    stem, ext = name.rsplit(".", 1)
    i = 2
    while True:
        candidate = f"{stem}_{i}.{ext}"
        if candidate not in seen:
            seen.add(candidate)
            return candidate
        i += 1


def process_pdf(pdf_bytes: bytes, filename: str) -> tuple:
    """
    Returns (Invoice, edi_text, edi_filename, warnings)
    Pipeline: pdfplumber → OCR fallback
    """
    warnings = []
    inv = None

    text = extract_text_pdfplumber(pdf_bytes)
    if len(text) > 80:
        inv = parse_invoice(text)
        inv.raw_text = text

    if OCR_AVAILABLE and (not inv or not inv.invoice_number):
        ocr_text = extract_text_ocr(pdf_bytes)
        if len(ocr_text) > 80:
            warnings.append("Used OCR for text extraction.")
            inv = parse_invoice(ocr_text)
            inv.raw_text = ocr_text
            inv.parse_method += " (OCR)"

    if not inv:
        inv = Invoice(vendor="UNKNOWN", vendor_code="UNKNWN", parse_method="failed")
        warnings.append("Could not extract invoice data. Install pytesseract for scanned PDF support.")

    return inv, invoice_to_edi(inv), _edi_filename(inv, filename), warnings


# ══════════════════════════════════════════════════════════════════════════════
# STREAMLIT UI
# ══════════════════════════════════════════════════════════════════════════════

def render_invoice_card(inv: Invoice):
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("Vendor", inv.vendor or "Unknown")
        st.metric("Invoice #", inv.invoice_number or "—")
    with col_b:
        st.metric("Date", inv.date.strftime("%m/%d/%Y") if inv.date else "—")
        st.metric("Total", f"${inv.total:,.2f}" if inv.total else "—")
    with col_c:
        st.metric("Line Items", len(inv.items))
        st.metric("Taxes / Fees", f"${inv.taxes:,.2f}" if inv.taxes else "—")
    st.caption(f"Parse method: {inv.parse_method}")


def render_items_table(items):
    import pandas as pd
    if not items:
        st.info("No line items extracted.")
        return
    st.dataframe(
        pd.DataFrame([{
            "Description": it.description,
            "UPC": it.upc or "—",
            "Cases": it.cases or "—",
            "Qty": it.quantity or "—",
            "Unit $": f"${it.unit_price:.2f}" if it.unit_price else "—",
            "Net $": f"${it.net_amount:.2f}",
        } for it in items]),
        use_container_width=True,
        hide_index=True,
    )


def main():
    st.set_page_config(page_title="PDF → EDI Converter", page_icon="📄", layout="wide")

    with st.sidebar:
        st.title("Settings")
        st.subheader("Extraction")
        st.write(f"pdfplumber: on")
        st.write(f"OCR (pytesseract): {'on' if OCR_AVAILABLE else 'off — install tesseract'}")
        st.divider()
        st.subheader("EDI Format")
        st.code(
            "A{vendor:9}{inv:7}{MMDDYY:6}{amt:10}\n"
            "B{code:6}{qty:5}{desc:25}{upc:12}  {seq:6}{amt:13}\n"
            "C{desc:28}{amt:9}",
            language="text",
        )
        st.caption("Amounts = sign + zero-padded cents")

    st.title("📄 PDF Invoice → EDI Converter")
    st.markdown("Upload any PDF invoice — the app scans, parses, and outputs a fixed-width EDI file.")

    tab_single, tab_bulk = st.tabs(["Single File", "Bulk"])

    # ── Single ────────────────────────────────────────────────────────────────
    with tab_single:
        uploaded = st.file_uploader("Drop a PDF invoice here", type=["pdf"], key="single")

        if uploaded:
            with st.spinner("Scanning…"):
                inv, edi_text, edi_filename, warnings = process_pdf(uploaded.read(), uploaded.name)

            for w in warnings:
                st.warning(w)

            st.subheader("Parsed Invoice")
            render_invoice_card(inv)
            st.divider()

            st.subheader(f"Line Items ({len(inv.items)})")
            render_items_table(inv.items)
            st.divider()

            st.subheader(f"EDI Output — {edi_filename}")
            st.code(edi_text, language="text")
            st.download_button(
                label=f"Download {edi_filename}",
                data=edi_text,
                file_name=edi_filename,
                mime="text/plain",
                use_container_width=True,
                type="primary",
            )

            with st.expander("Raw extracted text", expanded=False):
                st.text(inv.raw_text[:3000] + ("…" if len(inv.raw_text) > 3000 else ""))

    # ── Bulk ──────────────────────────────────────────────────────────────────
    with tab_bulk:
        uploaded_files = st.file_uploader(
            "Drop multiple PDF invoices here",
            type=["pdf"],
            accept_multiple_files=True,
            key="bulk",
        )

        if uploaded_files:
            if st.button("Process All", type="primary", use_container_width=True):
                results = []
                seen_names: set = set()
                bar = st.progress(0.0)
                status = st.empty()

                for idx, f in enumerate(uploaded_files, 1):
                    status.text(f"Processing {f.name} ({idx}/{len(uploaded_files)})…")
                    try:
                        inv, edi_text, edi_fn, warns = process_pdf(f.read(), f.name)
                        edi_fn = _unique(edi_fn, seen_names)   # guarantee distinct filename
                        results.append(dict(name=f.name, inv=inv, edi_text=edi_text,
                                            edi_fn=edi_fn, warns=warns, ok=True))
                    except Exception as exc:
                        results.append(dict(name=f.name, inv=None, edi_text="",
                                            edi_fn="", warns=[str(exc)], ok=False))
                    bar.progress(idx / len(uploaded_files))

                status.success(f"Done — {len(results)} file(s) processed.")

                import pandas as pd
                summary = []
                for r in results:
                    if r["inv"]:
                        i = r["inv"]
                        summary.append({
                            "PDF": r["name"], "EDI File": r["edi_fn"],
                            "Vendor": i.vendor or "—", "Invoice #": i.invoice_number or "—",
                            "Date": i.date.strftime("%m/%d/%Y") if i.date else "—",
                            "Items": len(i.items),
                            "Total": f"${i.total:,.2f}" if i.total else "—",
                            "Status": "OK",
                        })
                    else:
                        summary.append({"PDF": r["name"], "EDI File": "—", "Vendor": "—",
                                        "Invoice #": "—", "Date": "—", "Items": 0,
                                        "Total": "—", "Status": "Failed"})

                st.subheader("Summary")
                st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)

                st.subheader("EDI Files")
                for r in results:
                    label = f"{r['edi_fn']}  ←  {r['name']}" if r["edi_fn"] else f"Failed: {r['name']}"
                    with st.expander(label):
                        for w in r["warns"]:
                            st.warning(w)
                        if r["edi_text"]:
                            st.code(r["edi_text"], language="text")

                good = [r for r in results if r["edi_text"]]
                if good:
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                        for r in good:
                            zf.writestr(r["edi_fn"], r["edi_text"])
                    buf.seek(0)
                    st.download_button(
                        label=f"Download all {len(good)} EDI files (.zip)",
                        data=buf.getvalue(),
                        file_name="edi_export.zip",
                        mime="application/zip",
                        type="primary",
                        use_container_width=True,
                    )


if __name__ == "__main__":
    main()

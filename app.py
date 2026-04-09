import streamlit as st
import pdfplumber
import re
import os
import io
import json
import zipfile
import base64
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ── Optional: OCR ──────────────────────────────────────────────────────────────
try:
    from pdf2image import convert_from_bytes
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# ── Optional: Gemini ───────────────────────────────────────────────────────────
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# ══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class LineItem:
    description: str = ""
    upc: str = ""
    item_code: str = ""
    cases: int = 0
    units: int = 0
    quantity: int = 0
    unit_price: float = 0.0
    net_amount: float = 0.0


@dataclass
class Invoice:
    vendor: str = ""
    vendor_code: str = ""
    invoice_number: str = ""
    date: Optional[datetime] = None
    customer: str = ""
    store_number: str = ""
    items: list = field(default_factory=list)
    subtotal: float = 0.0
    taxes: float = 0.0
    total: float = 0.0
    raw_text: str = ""
    parse_method: str = ""


# ══════════════════════════════════════════════════════════════════════════════
# PDF TEXT EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_text_pdfplumber(pdf_bytes: bytes) -> str:
    """Extract text via pdfplumber (fast, works on text-based PDFs)."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
            return "\n".join(pages).strip()
    except Exception:
        return ""


def extract_text_ocr(pdf_bytes: bytes) -> str:
    """Extract text via pytesseract OCR (scanned PDFs, slower)."""
    if not OCR_AVAILABLE:
        return ""
    try:
        images = convert_from_bytes(pdf_bytes, dpi=300)
        return "\n".join(
            pytesseract.image_to_string(img, config="--psm 6")
            for img in images
        ).strip()
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# GEMINI AI EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

GEMINI_PROMPT = """You are an invoice data extraction specialist. Extract ALL invoice information from this PDF and return ONLY valid JSON — no markdown fences, no extra text.

Required JSON structure:
{
  "vendor": "full vendor/company name",
  "vendor_code": "short 6-char code for vendor (e.g. PEPSI, CCBNE, POLEP)",
  "invoice_number": "invoice number as string",
  "date": "MM/DD/YYYY",
  "customer_name": "store/customer name",
  "store_number": "store number if present, else empty string",
  "items": [
    {
      "description": "product description (max 25 chars)",
      "upc": "UPC barcode digits only, 12 chars if available",
      "item_code": "vendor item/product code if available",
      "cases": <integer>,
      "units": <integer>,
      "quantity": <integer total units>,
      "unit_price": <float>,
      "net_amount": <float net line amount>
    }
  ],
  "subtotal": <float>,
  "taxes": <float total taxes and fees>,
  "total": <float amount due>
}

Rules:
- description must be ≤ 25 characters; truncate if longer
- upc must be digits only, no dashes
- All numeric fields must be numbers (not strings)
- If a field is unknown use "" for strings and 0 for numbers
- Include EVERY line item from the invoice"""


def gemini_extract(pdf_bytes: bytes, api_key: str) -> dict:
    """Use Gemini to extract structured invoice data from any PDF."""
    if not GEMINI_AVAILABLE or not api_key:
        return {}
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        pdf_part = {
            "inline_data": {
                "mime_type": "application/pdf",
                "data": base64.standard_b64encode(pdf_bytes).decode(),
            }
        }

        response = model.generate_content([pdf_part, GEMINI_PROMPT])
        raw = response.text.strip()

        # Strip markdown code blocks if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        return json.loads(raw)
    except Exception as e:
        return {"_error": str(e)}


def gemini_dict_to_invoice(data: dict) -> Invoice:
    """Convert Gemini JSON dict to Invoice object."""
    inv = Invoice(
        vendor=data.get("vendor", ""),
        vendor_code=data.get("vendor_code", data.get("vendor", "")[:6]).upper(),
        invoice_number=str(data.get("invoice_number", "")),
        customer=data.get("customer_name", ""),
        store_number=str(data.get("store_number", "")),
        subtotal=_f(data.get("subtotal")),
        taxes=_f(data.get("taxes")),
        total=_f(data.get("total")),
        parse_method="Gemini AI",
    )

    # Parse date
    date_str = str(data.get("date", ""))
    for fmt in ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"]:
        try:
            inv.date = datetime.strptime(date_str, fmt)
            break
        except ValueError:
            pass

    for d in data.get("items", []):
        item = LineItem(
            description=str(d.get("description", ""))[:25],
            upc=re.sub(r"\D", "", str(d.get("upc", "") or "")),
            item_code=str(d.get("item_code", "") or ""),
            cases=_i(d.get("cases")),
            units=_i(d.get("units")),
            quantity=_i(d.get("quantity")),
            unit_price=_f(d.get("unit_price")),
            net_amount=_f(d.get("net_amount")),
        )
        inv.items.append(item)

    return inv


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


# ══════════════════════════════════════════════════════════════════════════════
# VENDOR DETECTION
# ══════════════════════════════════════════════════════════════════════════════

VENDOR_MAP = {
    "PEPSI": ["PEPSI", "PEPSICO"],
    "CCBNE": ["COCA-COLA", "COCA COLA", "COCACOLA", "CCBNE"],
    "REDBUL": ["RED BULL", "REDBULL"],
    "MNSTR": ["MONSTER ENERGY", "MONSTER"],
    "DRPPR": ["DR PEPPER", "DR. PEPPER", "KEURIG DR"],
    "POLEP": ["J. POLEP", "JPOLEP", "J POLEP"],
}


def detect_vendor(text: str) -> str:
    text_up = text.upper()
    for code, keywords in VENDOR_MAP.items():
        if any(k in text_up for k in keywords):
            return code
    return "GNRC"


# ══════════════════════════════════════════════════════════════════════════════
# VENDOR-SPECIFIC PARSERS  (regex-based, fast)
# ══════════════════════════════════════════════════════════════════════════════

# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_date(text: str) -> Optional[datetime]:
    for pat, fmt in [
        (r"\b(\d{1,2}/\d{1,2}/\d{4})\b", "%m/%d/%Y"),
        (r"\b(\d{1,2}/\d{1,2}/\d{2})\b", "%m/%d/%y"),
        (r"\b(\d{4}-\d{2}-\d{2})\b", "%Y-%m-%d"),
    ]:
        m = re.search(pat, text)
        if m:
            try:
                return datetime.strptime(m.group(1), fmt)
            except ValueError:
                pass
    return None


def _find_amount(text: str, keywords: list) -> float:
    for kw in keywords:
        m = re.search(kw + r"[\s:]+\$?\s*([\d,]+\.?\d*)", text, re.IGNORECASE)
        if m:
            return _f(m.group(1).replace(",", ""))
    return 0.0


# ── Pepsi Parser ──────────────────────────────────────────────────────────────

def parse_pepsi(text: str) -> Invoice:
    inv = Invoice(
        vendor="PEPSICO BEVERAGES COMPANY",
        vendor_code="PEPSI",
        parse_method="pdfplumber+regex",
    )

    # Invoice number: #XXXXXXXX
    m = re.search(r"#\s*(\d{6,12})", text)
    if m:
        inv.invoice_number = m.group(1)

    inv.date = _find_date(text)

    inv.taxes = _find_amount(text, [r"State[/\s]*Local\s*Charges?", r"MA\s*ST\s*DEP"])
    inv.total = _find_amount(text, [r"Amount Due", r"Total"])

    inv.items = _parse_pepsi_items(text)
    if not inv.total and inv.items:
        inv.total = sum(i.net_amount for i in inv.items)

    return inv


def _parse_pepsi_items(text: str) -> list:
    """
    Pepsi line items are in blocks:
      <description>
      <UPC line>  [maybe inline with description]
      <price_per_unit>   <cases>  <units>  <unit_price>  <net_amount>
    """
    items = []

    # Find the SALES / ITEM DETAIL section
    section = text
    m = re.search(r"ITEM DETAIL.*?SALES\s*\n(.*?)(?=STATE|CREDITS|Amount Due)", section, re.DOTALL | re.IGNORECASE)
    if m:
        section = m.group(1)

    lines = [l.strip() for l in section.split("\n") if l.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]

        # UPC embedded in description line: "SOME PRODUCT X-XXXXX-XXXXX-X"
        upc_inline = re.search(r"(\d-\d{5}-\d{5}-\d|\d{12,13})", line)
        upc = re.sub(r"\D", "", upc_inline.group(1)) if upc_inline else ""

        # Description = everything before the UPC or the whole line
        desc = re.split(r"\s+\d-\d{5}-\d{5}-\d", line)[0].strip() if upc_inline else line

        # Next line(s): look for amounts like "50.00  1  12  21.00  21.65"
        # or "1  12  19.09" etc.
        amount_line = ""
        for j in range(i + 1, min(i + 4, len(lines))):
            if re.search(r"^\d+\.?\d*\s+\d+\s+\d+\s+[\d.]+\s+[\d.,]+", lines[j]):
                amount_line = lines[j]
                i = j
                break

        if not amount_line:
            i += 1
            continue

        parts = amount_line.split()
        try:
            # formats vary; last token is net amount, before last is unit_price
            # common: price_per_case  cases  units  unit_price  net
            net = _f(parts[-1].replace(",", ""))
            unit_price = _f(parts[-2])
            units = _i(parts[-3])
            cases = _i(parts[-4]) if len(parts) >= 5 else _i(parts[-3])

            if net <= 0:
                i += 1
                continue

            if not desc or len(desc) < 3 or desc[0].isdigit():
                i += 1
                continue

            items.append(LineItem(
                description=desc[:25],
                upc=upc[:12],
                cases=cases,
                units=units,
                quantity=cases * units if units else cases,
                unit_price=unit_price,
                net_amount=net,
            ))
        except (IndexError, ValueError):
            pass

        i += 1

    return items


# ── Coca-Cola Parser ──────────────────────────────────────────────────────────

def parse_cocacola(text: str) -> Invoice:
    inv = Invoice(
        vendor="COCA-COLA BEVERAGES NE",
        vendor_code="CCBNE",
        parse_method="pdfplumber+regex",
    )

    # INV # or INVOICE #
    for pat in [r"INV#?\s*(\d{7,12})", r"INVOICE#?\s*(\d{7,12})"]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            inv.invoice_number = m.group(1)
            break

    # VENDOR# or VENDOR #
    m = re.search(r"VENDOR#?\s*(\d+)", text, re.IGNORECASE)
    if m:
        inv.vendor_code = "CCBNE"

    inv.date = _find_date(text)
    inv.taxes = _find_amount(text, [r"MA CONTAINER", r"TAX"])
    inv.total = _find_amount(text, [r"AMOUNT (?:DUE|PAID)", r"TOTAL PRODUCTS"])

    inv.items = _parse_cocacola_items(text)
    if not inv.total and inv.items:
        inv.total = sum(i.net_amount for i in inv.items)

    return inv


def _parse_cocacola_items(text: str) -> list:
    """
    Coca-Cola rows look like:
      20 OZ 1-Ls 12 ADVANCED   1/24   1.20  35.90  35.90  0.00  0.00  35.90
    or the DELIVERY RECAP section with UPCs.
    """
    items = []

    # Look for lines that end with a dollar amount and have multiple numbers
    for line in text.split("\n"):
        line = line.strip()
        # Expect at least 4 numeric tokens at the end
        numbers = re.findall(r"[-]?\d+\.\d+", line)
        if len(numbers) < 2:
            continue

        # Last number is net amount
        try:
            net = _f(numbers[-1])
        except (ValueError, IndexError):
            continue

        if net <= 0:
            continue

        # Strip numbers from description
        desc_part = re.sub(r"\s+\d+/\d+\s+.*$", "", line).strip()
        desc_part = re.sub(r"\s+[\d.]+.*$", "", desc_part).strip()
        if not desc_part or len(desc_part) < 4:
            continue

        # Skip header lines
        if re.match(r"(DESCRIPTION|QTY|NET|RATE|PRICE|EXTENDED)", desc_part, re.IGNORECASE):
            continue

        items.append(LineItem(
            description=desc_part[:25],
            net_amount=net,
        ))

    return items


# ── J. Polep Parser ───────────────────────────────────────────────────────────

def parse_polep(text: str) -> Invoice:
    inv = Invoice(
        vendor="J. POLEP DISTRIBUTION SERVICES",
        vendor_code="JPOLEP",
        parse_method="pdfplumber+regex",
    )

    # Invoice number from REPRINT/XXXXXX/ or standalone
    m = re.search(r"REPRINT/(\d+)/", text)
    if not m:
        m = re.search(r"INVOICE[#\s]*(\d{5,8})", text, re.IGNORECASE)
    if m:
        inv.invoice_number = m.group(1)

    inv.date = _find_date(text)

    # Total: from the summary row — invoice# date page# due_date amount-
    m = re.search(
        r"\d{5,8}\s+\d{1,2}/\d{1,2}/\d{2,4}\s+\d+\s+\d{1,2}/\d{1,2}/\d{2,4}\s+([\d,]+\.\d+)-",
        text,
    )
    if m:
        inv.total = _f(m.group(1).replace(",", ""))

    # Taxes: any line containing TAX or EXCISE with a trailing amount-
    # Space before the capture group prevents greedy backtracking from eating leading digits
    for tm in re.finditer(r"(?:TAX|EXCISE|DEPOSIT)[^\n]* ([\d,]+\.\d+)-", text, re.IGNORECASE):
        inv.taxes += _f(tm.group(1).replace(",", ""))

    inv.items = _parse_polep_items(text)

    if not inv.total and inv.items:
        inv.total = sum(i.net_amount for i in inv.items) + inv.taxes

    return inv


def _parse_polep_items(text: str) -> list:
    """
    Polep line items:
      167742 1- CROWNS GOLD 100 BOX 10 200 1 84.90 20 84.90 67.92 67.92-
      item_code qty- description  <misc numbers> retail/unit GP% total_retail wholesale/unit extension-
    The extension (net amount) is always the last float followed by '-'.
    """
    items = []

    pattern = re.compile(
        r"^(\d{5,7})\s+(\d+)-\s+"      # item_code  qty-
        r"(.+?)\s+"                      # description (non-greedy, stops before numeric tail)
        r"\d+\s+\d+\s+\d+\s+"           # sell-unit / package counts
        r"[\d.]+\s+\d+\s+"              # retail/unit  GP%
        r"[\d.]+\s+"                     # total retail
        r"([\d.]+)\s+"                   # wholesale/unit
        r"([\d.]+)-\s*$",               # extension (net amount)
        re.MULTILINE,
    )

    for m in pattern.finditer(text):
        item_code = m.group(1)
        cases = _i(m.group(2))
        desc = m.group(3).strip()
        unit_price = _f(m.group(4))
        net_amount = _f(m.group(5))

        if net_amount <= 0:
            continue

        items.append(LineItem(
            description=desc[:25],
            item_code=item_code,
            cases=cases,
            quantity=cases,
            unit_price=unit_price,
            net_amount=net_amount,
        ))

    return items


# ── Generic fallback parser ───────────────────────────────────────────────────

def parse_generic(text: str, vendor_code: str = "GNRC") -> Invoice:
    inv = Invoice(
        vendor=vendor_code,
        vendor_code=vendor_code[:9],
        parse_method="pdfplumber+regex(generic)",
    )
    for pat in [r"INVOICE\s*#?\s*(\w[\w-]{3,})", r"INV\s*#?\s*(\w[\w-]{3,})",
                r"ORDER\s*#?\s*(\w[\w-]{3,})", r"#\s*(\d{4,})"]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            inv.invoice_number = m.group(1)
            break

    inv.date = _find_date(text)
    inv.taxes = _find_amount(text, [r"TAX(?:ES)?", r"EXCISE", r"SURCHARGE"])
    inv.total = _find_amount(text, [r"AMOUNT\s*DUE", r"BALANCE\s*DUE",
                                    r"TOTAL\s*DUE", r"GRAND\s*TOTAL", r"TOTAL"])
    inv.items = _parse_generic_items(text)
    if not inv.total and inv.items:
        inv.total = sum(i.net_amount for i in inv.items) + inv.taxes
    return inv


_GENERIC_SKIP = re.compile(
    r"^\s*(DESCRIPTION|ITEM\b|PRODUCT|QTY\b|QUANTITY|UNIT\b|PRICE|EXT|EXTENDED|"
    r"AMOUNT|TOTAL|SUBTOTAL|SUB\s*TOTAL|TAX|INVOICE|DATE|PAGE|DUE|BALANCE|"
    r"DISCOUNT|FREIGHT|SHIPPING|HANDLING|THANK|PLEASE|REMIT|TERMS|SHIP\s*TO|"
    r"BILL\s*TO|SOLD\s*TO|FROM|TO\b|PHONE|FAX|WWW|HTTP|@|NOTES?|COMMENTS?)",
    re.IGNORECASE,
)


def _parse_generic_items(text: str) -> list:
    """
    Heuristic line item extractor for any invoice format.
    Finds lines that end with a dollar amount and have meaningful descriptions.
    """
    items = []
    seen = set()

    for line in text.split("\n"):
        line = line.strip()
        if not line or len(line) < 6:
            continue
        if _GENERIC_SKIP.match(line):
            continue

        # Line must end with a dollar amount (with or without $ sign)
        m = re.search(r"\$?\s*([\d,]+\.\d{2})\s*$", line)
        if not m:
            continue

        net = _f(m.group(1).replace(",", ""))
        if net <= 0:
            continue

        # Strip the trailing amount to isolate the description
        desc = line[: m.start()].strip()
        # Remove a leading item/product code (all-digit or short alphanumeric token)
        desc = re.sub(r"^\S{1,12}\s+", lambda x: "" if re.match(r"^[\dA-Z#\-\.]+$", x.group().strip()) else x.group(), desc)
        desc = desc.strip()

        # Remove any quantity / unit-price tokens just before the net amount
        desc = re.sub(r"\s+[\d,]+\.?\d*\s*$", "", desc).strip()
        desc = re.sub(r"\s+\d+\s*$", "", desc).strip()

        if not desc or len(desc) < 3 or not re.search(r"[A-Za-z]", desc):
            continue

        # Avoid duplicate lines (e.g. subtotals that repeat a line)
        key = (desc[:20], round(net, 2))
        if key in seen:
            continue
        seen.add(key)

        # Try to extract a quantity from the line
        qty_m = re.search(r"\b(\d{1,4})\s+(?:EA|CS|CS\.|CASE|PACK|PK|BOX|EACH|PC|PCS)\b", line, re.IGNORECASE)
        qty = _i(qty_m.group(1)) if qty_m else 0

        items.append(LineItem(
            description=desc[:25],
            quantity=qty,
            net_amount=net,
        ))

    return items


# ══════════════════════════════════════════════════════════════════════════════
# EDI GENERATOR
# Matches the format of S0582971.TXT:
#   A{vendor:9}{invoice:7}{MMDDYY:6}{amount:10}
#   B{code:6}{qty:5}{desc:25}{upc:12}  {seq:6}{amount:13}
#   C{desc:28}{amount:9}
# Amounts: sign (always '-') + zero-padded cents (no decimal point)
# ══════════════════════════════════════════════════════════════════════════════

def _edi_amount(value: float, width: int) -> str:
    """Format as sign + (width-1) digit cents, e.g. $3.05 → '-000000305' (w=10)."""
    cents = round(abs(value) * 100)
    digits = str(cents).zfill(width - 1)
    if len(digits) > width - 1:
        digits = digits[-(width - 1):]
    return f"-{digits}"


def invoice_to_edi(inv: Invoice) -> str:
    lines = []

    # Sanitize invoice number: keep last 7 digits
    raw_inv = re.sub(r"\D", "", inv.invoice_number or "0")
    inv_num = raw_inv[-7:].zfill(7) if raw_inv else "0000000"

    # Date
    date_str = inv.date.strftime("%m%d%y") if inv.date else datetime.now().strftime("%m%d%y")

    # Vendor code: 9 chars right-padded
    vendor = (inv.vendor_code or "GNRC").upper()[:9].ljust(9)

    # Total amount (sum items if no explicit total)
    total = inv.total or sum(i.net_amount for i in inv.items)

    # ── A record ──────────────────────────────────────────────────────────────
    lines.append(f"A{vendor}{inv_num}{date_str}{_edi_amount(total, 10)}")

    # ── B records ─────────────────────────────────────────────────────────────
    for seq, item in enumerate(inv.items, start=1):
        # Item code: first 6 digits of UPC, else item_code, else zeros
        upc_clean = re.sub(r"\D", "", item.upc or "")
        code = upc_clean[:6] if upc_clean else (item.item_code or "").ljust(6)[:6] or "000000"

        qty = str(max(item.cases, item.quantity, 0)).zfill(5)[:5]

        desc = item.description[:25].ljust(25)

        upc_full = upc_clean[:12].ljust(12)

        seq_str = str(seq).zfill(6)

        lines.append(
            f"B{code}{qty}{desc}{upc_full}  {seq_str}{_edi_amount(item.net_amount, 13)}"
        )

    # ── C record (taxes/fees) ─────────────────────────────────────────────────
    if inv.taxes > 0:
        tax_desc = "TAXES AND FEES FOR A INVOICE"[:28].ljust(28)
        lines.append(f"C{tax_desc}{_edi_amount(inv.taxes, 9)}")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN PROCESSING PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def process_pdf(pdf_bytes: bytes, filename: str, gemini_key: str = "") -> tuple:
    """
    Returns (Invoice, edi_text: str, edi_filename: str, warnings: list[str])

    Pipeline:
      1. pdfplumber → regex vendor parsers
      2. OCR (pytesseract) if text extraction is poor
      3. Gemini AI (best quality, handles scanned/rotated/complex PDFs)
    """
    warnings = []
    inv = None

    # ── Step 1: pdfplumber ────────────────────────────────────────────────────
    text = extract_text_pdfplumber(pdf_bytes)
    if text and len(text) > 80:
        vendor_code = detect_vendor(text)
        if vendor_code == "PEPSI":
            inv = parse_pepsi(text)
        elif vendor_code == "CCBNE":
            inv = parse_cocacola(text)
        elif vendor_code == "POLEP":
            inv = parse_polep(text)
        else:
            inv = parse_generic(text, vendor_code)
        inv.raw_text = text

    # ── Step 2: OCR fallback ──────────────────────────────────────────────────
    if OCR_AVAILABLE and (not inv or not inv.invoice_number):
        ocr_text = extract_text_ocr(pdf_bytes)
        if ocr_text and len(ocr_text) > 80:
            warnings.append("Used OCR (pytesseract) for text extraction.")
            vendor_code = detect_vendor(ocr_text)
            if vendor_code == "PEPSI":
                inv = parse_pepsi(ocr_text)
            elif vendor_code == "CCBNE":
                inv = parse_cocacola(ocr_text)
            elif vendor_code == "POLEP":
                inv = parse_polep(ocr_text)
            else:
                inv = parse_generic(ocr_text, vendor_code)
            inv.raw_text = ocr_text
            inv.parse_method += " (OCR)"

    # ── Step 3: Gemini AI ─────────────────────────────────────────────────────
    # Always run Gemini if: key provided AND (no items found OR no invoice# OR explicitly scanned)
    run_gemini = bool(gemini_key) and (
        not inv
        or not inv.invoice_number
        or not inv.items
        or len(text) < 80          # likely scanned
    )

    if run_gemini:
        data = gemini_extract(pdf_bytes, gemini_key)
        if data and "_error" not in data:
            gemini_inv = gemini_dict_to_invoice(data)
            if gemini_inv.invoice_number or gemini_inv.items:
                # Merge: prefer Gemini fields when they're more complete
                if gemini_inv.invoice_number:
                    inv = gemini_inv
                    warnings.append("Used Gemini AI for extraction.")
        elif "_error" in data:
            warnings.append(f"Gemini error: {data['_error']}")

    # ── Fallback: empty invoice ───────────────────────────────────────────────
    if not inv:
        inv = Invoice(vendor="UNKNOWN", vendor_code="UNKNWN", parse_method="failed")
        warnings.append("Could not extract invoice data. Check the PDF or add a Gemini API key.")

    # ── EDI filename ──────────────────────────────────────────────────────────
    raw_num = re.sub(r"\D", "", inv.invoice_number or "")
    if raw_num:
        edi_filename = f"S{raw_num[-7:].zfill(7)}.TXT"
    else:
        stem = Path(filename).stem[:7].upper().replace(" ", "")
        edi_filename = f"S{stem}.TXT"

    edi_text = invoice_to_edi(inv)
    return inv, edi_text, edi_filename, warnings


# ══════════════════════════════════════════════════════════════════════════════
# STREAMLIT UI
# ══════════════════════════════════════════════════════════════════════════════

def _status_badge(ok: bool) -> str:
    return "✅" if ok else "❌"


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
        st.metric("Taxes/Fees", f"${inv.taxes:,.2f}" if inv.taxes else "—")

    st.caption(f"Parse method: {inv.parse_method}")


def render_items_table(items):
    import pandas as pd
    if not items:
        st.info("No line items extracted.")
        return
    rows = []
    for item in items:
        rows.append({
            "Description": item.description,
            "UPC": item.upc or "—",
            "Cases": item.cases or "—",
            "Units": item.units or "—",
            "Qty": item.quantity or "—",
            "Unit $": f"${item.unit_price:.2f}" if item.unit_price else "—",
            "Net $": f"${item.net_amount:.2f}",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def main():
    st.set_page_config(
        page_title="PDF → EDI Converter",
        page_icon="📄",
        layout="wide",
    )

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.title("⚙️ Settings")

        gemini_key = st.text_input(
            "Google Gemini API Key",
            type="password",
            value=os.environ.get("GEMINI_API_KEY", ""),
            help=(
                "Required for scanned/rotated PDFs (e.g. Coca-Cola). "
                "Get a free key at https://aistudio.google.com/"
            ),
        )

        st.divider()
        st.subheader("Status")
        st.write(f"{_status_badge(True)} pdfplumber")
        st.write(f"{_status_badge(OCR_AVAILABLE)} OCR (pytesseract)")
        st.write(f"{_status_badge(GEMINI_AVAILABLE)} google-generativeai")
        st.write(f"{_status_badge(bool(gemini_key))} Gemini API key set")

        st.divider()
        st.subheader("EDI Format")
        st.code(
            "A{vendor:9}{inv:7}{MMDDYY:6}{amt:10}\n"
            "B{code:6}{qty:5}{desc:25}{upc:12}  {seq:6}{amt:13}\n"
            "C{desc:28}{amt:9}",
            language="text",
        )
        st.caption("Amounts = sign + zero-padded cents")

    # ── Main area ─────────────────────────────────────────────────────────────
    st.title("📄 PDF Invoice → EDI Converter")
    st.markdown(
        "Upload any vendor PDF invoice. "
        "The app extracts invoice data and generates a fixed-width EDI file. "
        "Pepsi, Coca-Cola, and J. Polep have dedicated parsers; all other vendors "
        "use a universal heuristic parser (or Gemini AI if a key is provided)."
    )

    tab_single, tab_bulk = st.tabs(["📎 Single File", "📦 Bulk (multiple files)"])

    # ══ TAB 1: Single ═════════════════════════════════════════════════════════
    with tab_single:
        uploaded = st.file_uploader(
            "Drop a PDF invoice here", type=["pdf"], key="single"
        )

        if uploaded:
            pdf_bytes = uploaded.read()

            with st.spinner("Extracting & parsing…"):
                inv, edi_text, edi_filename, warnings = process_pdf(
                    pdf_bytes, uploaded.name, gemini_key=gemini_key
                )

            for w in warnings:
                st.warning(w)

            left, right = st.columns([1, 1])

            with left:
                st.subheader("📊 Parsed Invoice")
                render_invoice_card(inv)
                st.divider()
                with st.expander(f"Line Items ({len(inv.items)})", expanded=True):
                    render_items_table(inv.items)

                with st.expander("Raw extracted text", expanded=False):
                    st.text(inv.raw_text[:3000] + ("…" if len(inv.raw_text) > 3000 else ""))

            with right:
                st.subheader(f"📋 EDI Output — {edi_filename}")
                st.code(edi_text, language="text")
                st.download_button(
                    label=f"⬇️ Download {edi_filename}",
                    data=edi_text,
                    file_name=edi_filename,
                    mime="text/plain",
                    use_container_width=True,
                    type="primary",
                )

    # ══ TAB 2: Bulk ════════════════════════════════════════════════════════════
    with tab_bulk:
        uploaded_files = st.file_uploader(
            "Drop multiple PDF invoices here",
            type=["pdf"],
            accept_multiple_files=True,
            key="bulk",
        )

        if uploaded_files:
            if st.button("▶️ Process All", type="primary", use_container_width=True):
                results = []
                bar = st.progress(0.0)
                status = st.empty()

                for idx, f in enumerate(uploaded_files, 1):
                    status.text(f"Processing {f.name} ({idx}/{len(uploaded_files)})…")
                    try:
                        inv, edi_text, edi_fn, warns = process_pdf(
                            f.read(), f.name, gemini_key=gemini_key
                        )
                        results.append(
                            dict(name=f.name, inv=inv, edi_text=edi_text,
                                 edi_fn=edi_fn, warns=warns, ok=True)
                        )
                    except Exception as exc:
                        results.append(
                            dict(name=f.name, inv=None, edi_text="",
                                 edi_fn="", warns=[str(exc)], ok=False)
                        )
                    bar.progress(idx / len(uploaded_files))

                status.success(f"✅ Done — {len(results)} file(s) processed.")

                # ── Summary table ──────────────────────────────────────────────
                import pandas as pd
                summary = []
                for r in results:
                    if r["inv"]:
                        i = r["inv"]
                        summary.append({
                            "PDF": r["name"],
                            "EDI File": r["edi_fn"],
                            "Vendor": i.vendor or "—",
                            "Invoice #": i.invoice_number or "—",
                            "Date": i.date.strftime("%m/%d/%Y") if i.date else "—",
                            "Items": len(i.items),
                            "Total": f"${i.total:,.2f}" if i.total else "—",
                            "Status": "✅",
                        })
                    else:
                        summary.append({
                            "PDF": r["name"], "EDI File": "—", "Vendor": "—",
                            "Invoice #": "—", "Date": "—", "Items": 0,
                            "Total": "—", "Status": "❌",
                        })

                st.subheader("Summary")
                st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)

                # ── Per-file expandable details ────────────────────────────────
                st.subheader("EDI Files")
                for r in results:
                    label = f"📄 {r['edi_fn']} ← {r['name']}" if r["edi_fn"] else f"❌ {r['name']}"
                    with st.expander(label):
                        for w in r["warns"]:
                            st.warning(w)
                        if r["edi_text"]:
                            st.code(r["edi_text"], language="text")

                # ── ZIP download ───────────────────────────────────────────────
                good = [r for r in results if r["edi_text"]]
                if good:
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                        for r in good:
                            zf.writestr(r["edi_fn"], r["edi_text"])
                    buf.seek(0)
                    st.download_button(
                        label=f"⬇️ Download all {len(good)} EDI files (.zip)",
                        data=buf.getvalue(),
                        file_name="edi_export.zip",
                        mime="application/zip",
                        type="primary",
                        use_container_width=True,
                    )


if __name__ == "__main__":
    main()

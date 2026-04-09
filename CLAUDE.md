# CLAUDE.md

## Project

PDF → EDI Converter. A single-file Streamlit app (`app.py`) that parses any vendor PDF invoice and outputs a fixed-width EDI text file.

## Architecture

All logic lives in `app.py`. No external config files, no database.

```
app.py
├── Data models          LineItem, Invoice (dataclasses)
├── Text extraction      extract_text_pdfplumber, extract_text_ocr
├── Gemini backend       gemini_extract, gemini_dict_to_invoice (unused in UI, kept for future use)
├── Universal parser     parse_invoice → _extract_line_items (two-pass)
├── EDI generator        invoice_to_edi, _edi_amount
├── Pipeline             process_pdf (pdfplumber → OCR fallback)
└── Streamlit UI         main, render_invoice_card, render_items_table
```

## Parsing approach

No vendor-specific branches. One universal parser handles all PDFs:

- **Pass 1 (structured rows):** matches lines starting with a 4–8 digit item code followed by qty, description, numeric columns, and a trailing net amount. Used for fixed-column distributor formats (e.g. J. Polep). If pass 1 finds items, pass 2 is skipped.
- **Pass 2 (amount-ending lines):** matches any line whose last token is a dollar amount. Used for standard invoice layouts.

Vendor code is derived automatically from the first line in the document that contains a business-type keyword (INC, LLC, DISTRIBUTION, BEVERAGES, etc.).

## EDI format

```
A{vendor:9}{invoice:7}{MMDDYY:6}{amount:10}
B{code:6}{qty:5}{desc:25}{upc:12}  {seq:6}{amount:13}
C{desc:28}{amount:9}
```

Amounts: sign character (`-`) + zero-padded cents, no decimal point.
Reference file: `S0582971.TXT`

## Key decisions

- No vendor map or vendor-specific parsers — the app is intentionally general.
- Gemini AI code is present in the file but not wired to the UI. It can be re-enabled by passing a key to `process_pdf` if needed.
- OCR requires system-level Tesseract + Poppler install (not a Python package).
- The `seen` set in `_extract_line_items` deduplicates items by (description prefix, net amount) to avoid category subtotal rows being double-counted.

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `streamlit` | Web UI |
| `pdfplumber` | PDF text extraction |
| `pdf2image` | Convert PDF pages to images for OCR |
| `pytesseract` | OCR engine wrapper |
| `pandas` | Table rendering |
| `Pillow` | Image handling for OCR |
| `google-generativeai` | Gemini AI (optional, not active in UI) |

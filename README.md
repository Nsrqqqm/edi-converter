# PDF → EDI Converter

A Streamlit web app that scans any vendor PDF invoice and generates a fixed-width EDI file.

## How it works

Upload a PDF invoice. The app extracts the text, parses it universally (no vendor-specific config needed), and outputs a fixed-width EDI file ready for import.

**Extraction pipeline:**
1. `pdfplumber` — fast text extraction for digital PDFs
2. `pytesseract` OCR — fallback for scanned/image-based PDFs (requires Tesseract installed)

**Vendor detection** is automatic — the app reads the company name from the document header and derives a 6-character vendor code. No vendor list to maintain.

## EDI Format

```
A{vendor:9}{invoice:7}{MMDDYY:6}{amount:10}
B{code:6}{qty:5}{desc:25}{upc:12}  {seq:6}{amount:13}
C{desc:28}{amount:9}
```

- `A` — invoice header (vendor, invoice number, date, total)
- `B` — one record per line item (item code, qty, description, UPC, net amount)
- `C` — taxes and fees (only emitted when taxes > 0)

Amounts are sign + zero-padded cents with no decimal point (e.g. `$194.09` → `-000019409`).

## Installation

```bash
pip install -r requirements.txt
```

**Optional: OCR support for scanned PDFs**

```bash
# macOS
brew install tesseract poppler

# Ubuntu / Debian
apt-get install tesseract-ocr poppler-utils
```

## Run

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

## Features

- Single file and bulk upload modes
- Bulk export downloads all EDI files as a ZIP
- Parsed invoice preview (vendor, invoice number, date, total, line items)
- Raw extracted text viewer for debugging

## Requirements

- Python 3.8+
- See `requirements.txt`

# CLAUDE.md

## Project

PDF → EDI Converter. A Next.js web app (`web/`) that parses any vendor PDF invoice and outputs a fixed-width EDI text file.

## Architecture

```
web/
├── app/api/convert/route.ts   API route — PDF upload → Invoice + EDI text
├── lib/types.ts               LineItem, Invoice, ConvertResponse interfaces
├── lib/edi.ts                 EDI generator (invoiceToEdi, ediAmount)
├── lib/gemini.ts              Gemini AI parser (invoice extraction)
├── components/UploadApp.tsx   Main UI (upload, display, download)
├── components/Dropzone.tsx    File drop zone
└── components/InvoiceDisplay.tsx  Invoice card + line items table
```

## Parsing approach

Gemini AI extracts invoice data from the PDF. No vendor-specific branches — one universal prompt handles all layouts.

## EDI format (ABC / J.Polep)

```
A{vendor:6}{invoice:10}{MMDDYY:6}{sign:1}{amount:9}
B{upc:11}{desc:25}{itemcode:6}{cost:6}{shipperflag:2}{pack:6}{sign:1}{qty:4}{retail:5}{filler:3}
C{chargetype:3}{desc:25}{sign:1}{amount:8}
```

Amounts: sign character (`-`) + zero-padded cents, no decimal point.
Reference spec: `web/ABC EDI Format.txt`

## Running locally

```bash
npm install
npm run dev
```

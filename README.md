# PDF → EDI Converter (Next.js)

Next.js port of the Streamlit app. Uses **Google Gemini 2.5 Flash** to extract
invoice data from any vendor PDF and generate a fixed-width EDI file. Designed
to deploy to **Vercel** as a single project.

## Features

- Single and bulk PDF upload with drag-and-drop
- Gemini-powered extraction — handles any vendor layout, including scanned PDFs
- Invoice preview (vendor, invoice #, date, totals, line items)
- Fixed-width EDI output (A / B / C records) in ABC / J.Polep format
- Download single EDI file or a ZIP of all bulk results

## Local development

```bash
cp .env.local.example .env.local
# edit .env.local and set GEMINI_API_KEY
npm install
npm run dev
```

Open http://localhost:3000.

## Deploy to Vercel

1. Push this repo to GitHub.
2. In the Vercel dashboard, **Import Project** and select the repo.
3. Framework preset: Next.js (auto-detected).
5. Under **Environment Variables**, add:
   - `GEMINI_API_KEY` = your key from https://aistudio.google.com/apikey
6. Deploy.

### Notes on limits

- Vercel serverless functions have a **4.5 MB request body limit** by default.
  Most vendor invoices fit comfortably, but very large scanned PDFs may be
  rejected. If this becomes an issue, upload directly to the Gemini Files API
  from the client instead of routing bytes through the serverless function.
- The `/api/convert` route is configured with `maxDuration = 60` seconds.
  Vercel Hobby caps at 60s, Pro allows up to 300s.

## EDI Format (ABC / J.Polep)

```
A{vendor:6}{inv:10}{MMDDYY:6}{sign:1}{amt:9}
B{upc:11}{desc:25}{itemcode:6}{cost:6}{shipperflag:2}{pack:6}{sign:1}{qty:4}{retail:5}{filler:3}
C{chargetype:3}{desc:25}{sign:1}{amt:8}
```

Amounts are sign character (`-`) + zero-padded cents, no decimal point
(e.g. `$194.09` → `-000019409`).

## Project layout

```
├── app/
│   ├── api/convert/route.ts    POST endpoint: PDF → Gemini → EDI
│   ├── globals.css
│   ├── layout.tsx
│   └── page.tsx
├── components/
│   ├── Dropzone.tsx            Drag-and-drop file input
│   ├── InvoiceDisplay.tsx      Parsed invoice card + items table + EDI pre
│   └── UploadApp.tsx           Tabs + single/bulk flows
├── lib/
│   ├── edi.ts                  EDI generator (ABC / J.Polep format)
│   ├── gemini.ts               Gemini extraction with typed JSON schema
│   └── types.ts                Invoice / LineItem / ConvertResponse types
├── package.json
└── tsconfig.json
```

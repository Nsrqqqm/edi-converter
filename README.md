# PDF → EDI Converter (Next.js)

Next.js port of the Streamlit app. Uses **Google Gemini 2.5 Flash** to extract
invoice data from any vendor PDF and generate a fixed-width EDI file. Designed
to deploy to **Vercel** as a single project.

## Features

- Single and bulk PDF upload with drag-and-drop
- Gemini-powered extraction — handles any vendor layout, including scanned PDFs
- Invoice preview (vendor, invoice #, date, totals, line items)
- Fixed-width EDI output (A / B / C records), identical format to the Python
  version
- Download single EDI file or a ZIP of all bulk results

## Local development

```bash
cd web
cp .env.local.example .env.local
# edit .env.local and set GEMINI_API_KEY
npm install
npm run dev
```

Open http://localhost:3000.

## Deploy to Vercel

1. Push this repo to GitHub.
2. In the Vercel dashboard, **Import Project** and select the repo.
3. Set the **Root Directory** to `web`.
4. Framework preset: Next.js (auto-detected).
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

## EDI Format

```
A{vendor:9}{inv:7}{MMDDYY:6}{amt:10}
B{code:6}{qty:5}{desc:25}{upc:12}  {seq:6}{amt:13}
C{desc:28}{amt:9}
```

Amounts are sign character + zero-padded cents, no decimal point
(e.g. `$194.09` → `-000019409`).

## Project layout

```
web/
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
│   ├── edi.ts                  EDI generator (ported from app.py)
│   ├── gemini.ts               Gemini extraction with typed JSON schema
│   └── types.ts                Invoice / LineItem / ConvertResponse types
├── package.json
└── tsconfig.json
```

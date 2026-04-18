/**
 * Gemini invoice extraction.
 *
 * Sends a PDF to Gemini 2.5 Flash as inline base64 data and asks for a
 * strictly-typed JSON response matching the Invoice schema.
 */

import { GoogleGenAI, Type } from "@google/genai";
import type { Invoice } from "./types";

const MODEL = "gemini-2.5-flash";

const INVOICE_SCHEMA = {
  type: Type.OBJECT,
  properties: {
    vendor: {
      type: Type.STRING,
      description: "Vendor / seller company name as printed on the invoice.",
    },
    vendorCode: {
      type: Type.STRING,
      description:
        "Short uppercase alphanumeric code (max 9 chars) derived from the vendor name. Strip punctuation, spaces, and legal suffixes like INC/LLC/CORP.",
    },
    invoiceNumber: {
      type: Type.STRING,
      description: "Invoice number, reference number, or document number.",
    },
    date: {
      type: Type.STRING,
      description:
        "Invoice date in strict YYYY-MM-DD format. Return an empty string if unknown.",
    },
    items: {
      type: Type.ARRAY,
      description:
        "Real product/line items on the invoice. Do NOT include subtotal rows, category headers (e.g. BEER, WINE), tax rows, freight, shipping, handling, or running totals.",
      items: {
        type: Type.OBJECT,
        properties: {
          description: {
            type: Type.STRING,
            description: "Product description, trimmed of extra whitespace.",
          },
          itemCode: {
            type: Type.STRING,
            description: "Vendor item code / SKU if present, else empty.",
          },
          upc: {
            type: Type.STRING,
            description: "UPC / GTIN / barcode digits if present, else empty.",
          },
          cases: {
            type: Type.NUMBER,
            description: "Number of cases ordered. 0 if not applicable.",
          },
          quantity: {
            type: Type.NUMBER,
            description:
              "Total unit quantity. If the invoice has only one quantity column, set this to the same value as cases.",
          },
          unitPrice: {
            type: Type.NUMBER,
            description: "Unit price in dollars. 0 if not shown.",
          },
          netAmount: {
            type: Type.NUMBER,
            description: "Net / extended line amount in dollars.",
          },
        },
        required: ["description", "netAmount"],
      },
    },
    taxes: {
      type: Type.NUMBER,
      description:
        "Sum of taxes, surcharges, excise, and deposits on the invoice. 0 if none.",
    },
    total: {
      type: Type.NUMBER,
      description: "Grand total / amount due in dollars.",
    },
  },
  required: ["vendor", "invoiceNumber", "items", "total"],
};

const PROMPT = `You are an expert invoice data extractor.

Extract structured data from the attached vendor invoice PDF and return strict JSON matching the provided schema.

Rules:
- Line items must only include real product rows. Skip subtotals, category headers, tax rows, freight, shipping, handling, and any row that is clearly a running total.
- Dollar values must be plain numbers (no $, no commas). Negative line items stay negative.
- If a field is unknown, return an empty string for strings or 0 for numbers.
- "date" must be YYYY-MM-DD or an empty string.
- "vendorCode" is a short uppercase alphanumeric code (max 9 chars) derived from the vendor name.
- "cases" and "quantity": if the invoice only has one quantity column, set both to the same value.`;

export async function extractInvoiceFromPdf(
  pdfBytes: Uint8Array | Buffer,
): Promise<Invoice> {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    throw new Error(
      "GEMINI_API_KEY is not set. Add it to your environment (e.g. .env.local or Vercel project settings).",
    );
  }

  const ai = new GoogleGenAI({ apiKey });
  const base64 = Buffer.from(pdfBytes).toString("base64");

  const response = await ai.models.generateContent({
    model: MODEL,
    contents: [
      {
        role: "user",
        parts: [
          { inlineData: { mimeType: "application/pdf", data: base64 } },
          { text: PROMPT },
        ],
      },
    ],
    config: {
      responseMimeType: "application/json",
      responseSchema: INVOICE_SCHEMA,
      temperature: 0.1,
    },
  });

  const text = response.text;
  if (!text) {
    throw new Error("Gemini returned an empty response.");
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (err) {
    throw new Error(
      `Failed to parse Gemini JSON output: ${(err as Error).message}`,
    );
  }

  return normalizeInvoice(parsed);
}

function normalizeInvoice(raw: unknown): Invoice {
  const r = (raw ?? {}) as Record<string, unknown>;
  const rawItems = Array.isArray(r.items) ? (r.items as unknown[]) : [];
  const dateStr = String(r.date ?? "").trim();
  const dateValid = /^\d{4}-\d{2}-\d{2}$/.test(dateStr) ? dateStr : null;

  return {
    vendor: String(r.vendor ?? "").trim(),
    vendorCode: String(r.vendorCode ?? "").trim(),
    invoiceNumber: String(r.invoiceNumber ?? "").trim(),
    date: dateValid,
    items: rawItems.map((raw) => {
      const it = (raw ?? {}) as Record<string, unknown>;
      return {
        description: String(it.description ?? "").trim(),
        itemCode: String(it.itemCode ?? "").trim(),
        upc: String(it.upc ?? "").trim(),
        cases: toNum(it.cases),
        quantity: toNum(it.quantity),
        unitPrice: toNum(it.unitPrice),
        netAmount: toNum(it.netAmount),
      };
    }),
    taxes: toNum(r.taxes),
    total: toNum(r.total),
  };
}

function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

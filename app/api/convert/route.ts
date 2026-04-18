import { NextRequest, NextResponse } from "next/server";
import { extractInvoiceFromPdf } from "@/lib/gemini";
import { ediFilename, invoiceToEdi } from "@/lib/edi";
import type { ConvertResponse } from "@/lib/types";

export const runtime = "nodejs";
export const maxDuration = 60;

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const file = formData.get("file");

    if (!file || !(file instanceof File)) {
      return NextResponse.json(
        {
          error:
            "Missing file. Send as multipart/form-data with form field 'file'.",
        },
        { status: 400 },
      );
    }

    if (!file.name.toLowerCase().endsWith(".pdf")) {
      return NextResponse.json(
        { error: "Only .pdf files are supported." },
        { status: 415 },
      );
    }

    const arrayBuffer = await file.arrayBuffer();
    const pdfBytes = new Uint8Array(arrayBuffer);

    const invoice = await extractInvoiceFromPdf(pdfBytes);
    const ediText = invoiceToEdi(invoice);
    const filename = ediFilename(invoice, file.name);

    const payload: ConvertResponse = {
      invoice,
      ediText,
      ediFilename: filename,
      warnings: [],
    };

    return NextResponse.json(payload);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    console.error("[/api/convert]", err);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

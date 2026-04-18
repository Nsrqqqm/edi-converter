/**
 * EDI generator — ABC / J.Polep format.
 *
 * A{vendor:6}{invoice:10}{MMDDYY:6}{sign:1}{amount:9}
 * B{upc:11}{desc:25}{itemcode:6}{cost:6}{shipperflag:2}{pack:6}{sign:1}{qty:4}{retail:5}{filler:3}
 * C{chargetype:3}{desc:25}{sign:1}{amount:8}
 */

import type { Invoice } from "./types";

/** Sign character ('-') + zero-padded cents, width chars total. */
export function ediAmount(value: number, width: number): string {
  const cents = Math.round(Math.abs(value) * 100);
  const padded = String(cents).padStart(width - 1, "0").slice(-(width - 1));
  return `-${padded}`;
}

function parseDateYmd(s: string | null | undefined): Date | null {
  if (!s) return null;
  const m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatMmddyy(date: Date): string {
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  const yy = String(date.getFullYear() % 100).padStart(2, "0");
  return `${mm}${dd}${yy}`;
}

export function invoiceToEdi(inv: Invoice): string {
  const lines: string[] = [];

  const rawInv = (inv.invoiceNumber || "0").replace(/\D/g, "");
  const invNum = rawInv.slice(-10).padStart(10, "0") || "0000000000";

  const parsedDate = parseDateYmd(inv.date) ?? new Date();
  const dateStr = formatMmddyy(parsedDate);

  const vendor = (inv.vendorCode || "GNRC").toUpperCase().slice(0, 6).padEnd(6);

  const total =
    inv.total || inv.items.reduce((sum, i) => sum + (i.netAmount || 0), 0);

  // A record
  lines.push(`A${vendor}${invNum}${dateStr}${ediAmount(total, 10)}`);

  inv.items.forEach((item) => {
    const upcRaw = (item.upc || "").replace(/\D/g, "");
    let upc11: string;
    if (upcRaw) {
      upc11 = upcRaw.padStart(11, "0").slice(-11);
    } else {
      const digits = (item.itemCode || "").replace(/\D/g, "");
      upc11 = digits ? digits.padStart(11, "0").slice(-11) : "00000000000";
    }

    const desc25     = (item.description || "").slice(0, 25).padEnd(25);
    const itemCode6  = (item.itemCode || "").slice(0, 6).padEnd(6);
    const costCents  = Math.round(Math.abs(item.unitPrice || 0) * 100);
    const cost6      = String(costCents).padStart(6, "0").slice(-6);
    const pack6      = String(Math.max(item.cases || 0, 0)).padStart(6, "0").slice(-6);
    const q          = Math.max(item.quantity || 0, item.cases || 0, 0);
    const qty4       = String(q).padStart(4, "0").slice(-4);
    const retail5    = String(costCents).padStart(5, "0").slice(-5);

    // B record
    lines.push(
      `B${upc11}${desc25}${itemCode6}${cost6}  ${pack6}-${qty4}${retail5}001`,
    );
  });

  if (inv.taxes > 0) {
    // C record
    const desc25 = "TAXES AND FEES".slice(0, 25).padEnd(25);
    lines.push(`CTAX${desc25}${ediAmount(inv.taxes, 9)}`);
  }

  return lines.join("\n");
}

export function ediFilename(inv: Invoice, sourceFilename: string): string {
  const rawNum = (inv.invoiceNumber || "").replace(/\D/g, "");
  if (rawNum) {
    return `S${rawNum.slice(-7).padStart(7, "0")}.TXT`;
  }
  const stem = sourceFilename
    .replace(/\.[^.]+$/, "")
    .slice(0, 7)
    .toUpperCase()
    .replace(/ /g, "");
  return `S${stem}.TXT`;
}

/** Return `name` unchanged if not in `seen`, else append `_2`, `_3`, ... until unique. */
export function uniqueFilename(name: string, seen: Set<string>): string {
  if (!seen.has(name)) {
    seen.add(name);
    return name;
  }
  const lastDot = name.lastIndexOf(".");
  const stem = lastDot >= 0 ? name.slice(0, lastDot) : name;
  const ext = lastDot >= 0 ? name.slice(lastDot + 1) : "";
  let i = 2;
  while (true) {
    const candidate = ext ? `${stem}_${i}.${ext}` : `${stem}_${i}`;
    if (!seen.has(candidate)) {
      seen.add(candidate);
      return candidate;
    }
    i++;
  }
}

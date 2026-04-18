"use client";

import { useState } from "react";
import JSZip from "jszip";
import { Dropzone } from "./Dropzone";
import { InvoiceDisplay } from "./InvoiceDisplay";
import type { ConvertResponse } from "@/lib/types";

type Tab = "single" | "bulk";

export default function UploadApp() {
  const [tab, setTab] = useState<Tab>("single");

  return (
    <div className="mt-8">
      <div className="mb-6 inline-flex gap-1 rounded-lg border border-gray-200 p-1 dark:border-gray-800">
        <TabButton active={tab === "single"} onClick={() => setTab("single")}>
          Single file
        </TabButton>
        <TabButton active={tab === "bulk"} onClick={() => setTab("bulk")}>
          Bulk
        </TabButton>
      </div>
      {tab === "single" ? <SinglePanel /> : <BulkPanel />}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "rounded-md px-4 py-1.5 text-sm font-medium transition-colors",
        active
          ? "bg-blue-600 text-white"
          : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

async function convertOne(file: File): Promise<ConvertResponse> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/convert", { method: "POST", body: fd });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data?.error || `Request failed with status ${res.status}`);
  }
  return data as ConvertResponse;
}

// ── Single ───────────────────────────────────────────────────────────────────

function SinglePanel() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ConvertResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filename, setFilename] = useState<string>("");

  const onFiles = async (files: File[]) => {
    const f = files[0];
    if (!f) return;
    setFilename(f.name);
    setResult(null);
    setError(null);
    setLoading(true);
    try {
      const res = await convertOne(f);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section>
      <Dropzone onFiles={onFiles} disabled={loading} />
      {loading && (
        <p className="mt-6 text-sm text-gray-500">
          Scanning <span className="font-mono">{filename}</span> with Gemini…
        </p>
      )}
      {error && (
        <div className="mt-6 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
          <strong>Error:</strong> {error}
        </div>
      )}
      {result && <InvoiceDisplay result={result} />}
    </section>
  );
}

// ── Bulk ─────────────────────────────────────────────────────────────────────

type BulkEntry = {
  file: File;
  status: "pending" | "processing" | "done" | "error";
  result?: ConvertResponse;
  error?: string;
};

function BulkPanel() {
  const [entries, setEntries] = useState<BulkEntry[]>([]);
  const [running, setRunning] = useState(false);

  const onFiles = (files: File[]) => {
    setEntries(files.map((file) => ({ file, status: "pending" })));
  };

  const processAll = async () => {
    setRunning(true);
    const seen = new Set<string>();
    const next = [...entries];
    for (let i = 0; i < next.length; i++) {
      next[i] = { ...next[i], status: "processing" };
      setEntries([...next]);
      try {
        const result = await convertOne(next[i].file);
        result.ediFilename = uniqueName(result.ediFilename, seen);
        next[i] = { ...next[i], status: "done", result };
      } catch (err) {
        next[i] = {
          ...next[i],
          status: "error",
          error: err instanceof Error ? err.message : String(err),
        };
      }
      setEntries([...next]);
    }
    setRunning(false);
  };

  const downloadZip = async () => {
    const zip = new JSZip();
    for (const e of entries) {
      if (e.result) {
        zip.file(e.result.ediFilename, e.result.ediText);
      }
    }
    const blob = await zip.generateAsync({ type: "blob" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "edi_export.zip";
    a.click();
    URL.revokeObjectURL(url);
  };

  const doneCount = entries.filter((e) => e.status === "done").length;
  const allProcessed =
    entries.length > 0 &&
    entries.every((e) => e.status === "done" || e.status === "error");

  return (
    <section>
      <Dropzone multiple onFiles={onFiles} disabled={running} />

      {entries.length > 0 && (
        <div className="mt-6 space-y-4">
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              disabled={running}
              onClick={processAll}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {running
                ? `Processing… (${doneCount}/${entries.length})`
                : `Process all (${entries.length})`}
            </button>
            {allProcessed && doneCount > 0 && (
              <button
                type="button"
                onClick={downloadZip}
                className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800"
              >
                Download {doneCount} EDI files as .zip
              </button>
            )}
          </div>

          <div className="overflow-x-auto rounded-md border border-gray-200 dark:border-gray-800">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900">
                <tr>
                  <Th>PDF</Th>
                  <Th>EDI File</Th>
                  <Th>Vendor</Th>
                  <Th>Invoice #</Th>
                  <Th>Date</Th>
                  <Th className="text-right">Items</Th>
                  <Th className="text-right">Total</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e, i) => (
                  <tr
                    key={i}
                    className="border-t border-gray-100 dark:border-gray-800"
                  >
                    <Td className="max-w-[16rem] truncate">{e.file.name}</Td>
                    <Td className="font-mono text-xs">
                      {e.result?.ediFilename ?? "—"}
                    </Td>
                    <Td>{e.result?.invoice.vendor || "—"}</Td>
                    <Td>{e.result?.invoice.invoiceNumber || "—"}</Td>
                    <Td>{e.result?.invoice.date || "—"}</Td>
                    <Td className="text-right">
                      {e.result?.invoice.items.length ?? "—"}
                    </Td>
                    <Td className="text-right">
                      {e.result?.invoice.total
                        ? `$${e.result.invoice.total.toFixed(2)}`
                        : "—"}
                    </Td>
                    <Td>
                      <StatusBadge status={e.status} />
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {entries.some((e) => e.error) && (
            <div className="space-y-2">
              {entries
                .filter((e) => e.error)
                .map((e, i) => (
                  <div
                    key={i}
                    className="rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
                  >
                    <strong>{e.file.name}:</strong> {e.error}
                  </div>
                ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function StatusBadge({ status }: { status: BulkEntry["status"] }) {
  const classes: Record<BulkEntry["status"], string> = {
    pending: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
    processing:
      "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
    done: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300",
    error: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${classes[status]}`}
    >
      {status}
    </span>
  );
}

function Th({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={`px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400 ${className}`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <td className={`px-3 py-2 ${className}`}>{children}</td>;
}

function uniqueName(name: string, seen: Set<string>): string {
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

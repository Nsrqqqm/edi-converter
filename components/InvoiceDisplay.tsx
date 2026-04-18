"use client";

import type { ConvertResponse } from "@/lib/types";

export function InvoiceDisplay({ result }: { result: ConvertResponse }) {
  const { invoice, ediText, ediFilename } = result;

  const download = () => {
    const blob = new Blob([ediText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = ediFilename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mt-8 space-y-8">
      <section>
        <h2 className="mb-3 text-lg font-semibold">Parsed Invoice</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Metric label="Vendor" value={invoice.vendor || "—"} />
          <Metric label="Invoice #" value={invoice.invoiceNumber || "—"} />
          <Metric label="Date" value={invoice.date ?? "—"} />
          <Metric
            label="Total"
            value={invoice.total ? `$${invoice.total.toFixed(2)}` : "—"}
          />
          <Metric label="Line items" value={String(invoice.items.length)} />
          <Metric
            label="Taxes / Fees"
            value={invoice.taxes ? `$${invoice.taxes.toFixed(2)}` : "—"}
          />
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">
          Line items ({invoice.items.length})
        </h2>
        {invoice.items.length === 0 ? (
          <p className="text-sm text-gray-500">No line items extracted.</p>
        ) : (
          <div className="overflow-x-auto rounded-md border border-gray-200 dark:border-gray-800">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900">
                <tr>
                  <Th>Description</Th>
                  <Th>UPC</Th>
                  <Th className="text-right">Cases</Th>
                  <Th className="text-right">Qty</Th>
                  <Th className="text-right">Unit $</Th>
                  <Th className="text-right">Net $</Th>
                </tr>
              </thead>
              <tbody>
                {invoice.items.map((it, i) => (
                  <tr
                    key={i}
                    className="border-t border-gray-100 dark:border-gray-800"
                  >
                    <Td>{it.description}</Td>
                    <Td className="font-mono text-xs">{it.upc || "—"}</Td>
                    <Td className="text-right">{it.cases || "—"}</Td>
                    <Td className="text-right">{it.quantity || "—"}</Td>
                    <Td className="text-right">
                      {it.unitPrice ? `$${it.unitPrice.toFixed(2)}` : "—"}
                    </Td>
                    <Td className="text-right">
                      ${it.netAmount.toFixed(2)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-lg font-semibold">
            EDI Output —{" "}
            <span className="font-mono text-base">{ediFilename}</span>
          </h2>
          <button
            type="button"
            onClick={download}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Download {ediFilename}
          </button>
        </div>
        <pre className="overflow-x-auto rounded-md bg-gray-900 p-4 font-mono text-xs text-gray-100">
          {ediText}
        </pre>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-gray-200 p-3 dark:border-gray-800">
      <div className="text-xs uppercase tracking-wide text-gray-500">
        {label}
      </div>
      <div className="mt-1 truncate text-base font-semibold">{value}</div>
    </div>
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

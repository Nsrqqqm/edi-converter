import UploadApp from "@/components/UploadApp";

export default function Home() {
  return (
    <main className="mx-auto max-w-5xl px-4 py-10 sm:px-6 lg:px-8">
      <header className="mb-2">
        <h1 className="text-3xl font-bold tracking-tight">
          PDF Invoice → EDI Converter
        </h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          Upload any vendor PDF invoice. Gemini extracts the line items and the
          app generates a fixed-width EDI file ready for import.
        </p>
      </header>

      <UploadApp />

      <section className="mt-16 rounded-lg border border-gray-200 p-5 dark:border-gray-800">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          EDI Format
        </h2>
        <pre className="mt-3 overflow-x-auto font-mono text-xs">
{`A{vendor:9}{inv:7}{MMDDYY:6}{amt:10}
B{code:6}{qty:5}{desc:25}{upc:12}  {seq:6}{amt:13}
C{desc:28}{amt:9}`}
        </pre>
        <p className="mt-3 text-xs text-gray-500">
          Amounts = sign character + zero-padded cents, no decimal point.
        </p>
      </section>
    </main>
  );
}

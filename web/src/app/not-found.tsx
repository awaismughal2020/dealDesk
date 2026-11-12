import Link from "next/link";

export default function NotFound() {
  return (
    <main id="main" className="mx-auto max-w-xl px-4 py-16">
      <h1 className="text-2xl font-bold">Page not found</h1>
      <p className="mt-2">
        <Link href="/" className="text-brand underline">
          Back to the dashboard
        </Link>
      </p>
    </main>
  );
}

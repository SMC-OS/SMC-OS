import { notFound } from "next/navigation";
import Link from "next/link";

import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { findLegalDocument, LEGAL_DOCUMENTS, LEGAL_EFFECTIVE_DATE, LEGAL_VERSION } from "@/lib/legal";

export function generateStaticParams() { return LEGAL_DOCUMENTS.map(({ slug }) => ({ slug })); }

export default async function LegalDocumentPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const document = findLegalDocument(slug);
  if (!document) notFound();
  return <><Nav /><main><section className="section section--tight"><div className="shell shell--narrow"><p className="eyebrow">Legal Centre</p><h1>{document.title}</h1><p className="section__lead">{document.summary}</p><p><small>Version {LEGAL_VERSION} · Effective {LEGAL_EFFECTIVE_DATE}</small></p></div></section><section className="section"><article className="shell shell--narrow legal-document">{document.sections.map((section) => <section key={section.heading}><h2>{section.heading}</h2>{section.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}{section.bullets && <ul>{section.bullets.map((item) => <li key={item}>{item}</li>)}</ul>}</section>)}<p><Link href="/legal">Return to the Legal Centre</Link></p></article></section></main><Footer /></>;
}

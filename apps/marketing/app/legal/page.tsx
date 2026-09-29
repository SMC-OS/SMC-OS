import Link from "next/link";
import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { LEGAL_DOCUMENTS, LEGAL_EFFECTIVE_DATE, LEGAL_VERSION } from "@/lib/legal";

export default function LegalPage() {
  return <><Nav /><main><section className="section section--tight"><div className="shell"><p className="eyebrow">GeoCore Legal Centre</p><h1>Clear information for using GeoCore</h1><p className="section__lead">Our product, privacy and data-processing information in one place. These documents are prepared for publication and remain subject to professional legal review.</p><p><small>Policy version {LEGAL_VERSION} · Effective {LEGAL_EFFECTIVE_DATE}</small></p></div></section><section className="section"><div className="shell"><div className="legal-index">{LEGAL_DOCUMENTS.map((document) => <article className="legal-index__item" key={document.slug}><h2><Link href={`/legal/${document.slug}`}>{document.title}</Link></h2><p>{document.summary}</p><Link href={`/legal/${document.slug}`}>Read {document.title}</Link></article>)}</div><p className="section__lead">Manage browser choices from Cookie preferences, or marketing email choices from Settings &gt; Privacy &amp; communications. For privacy requests, email <a href="mailto:privacy@geocore.one">privacy@geocore.one</a>.</p></div></section></main><Footer /></>;
}

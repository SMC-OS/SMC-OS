import Link from "next/link";

import { APP_URL } from "@/lib/site";

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="shell footer-grid">
        <div>
          <p className="footer-brand">GeoCore</p>
          <p>The Operating System for Stone &amp; Construction.</p>
          <p>© {new Date().getFullYear()} GeoCore</p>
        </div>

        <div>
          <p className="footer-heading">Product</p>
          <ul>
            <li>
              <Link href="/#product">What&apos;s inside</Link>
            </li>
            <li>
              <Link href="/#trades">Trade workflows</Link>
            </li>
            <li>
              <Link href="/pricing">Pricing</Link>
            </li>
          </ul>
        </div>

        <div>
          <p className="footer-heading">Get started</p>
          <ul>
            <li>
              <Link href="/pricing">Start 14-day trial</Link>
            </li>
            <li>
              <Link href="/request-demo">Request a demo</Link>
            </li>
            <li>
              <a href={`${APP_URL}/login`}>Sign in</a>
            </li>
          </ul>
        </div>
      </div>
    </footer>
  );
}

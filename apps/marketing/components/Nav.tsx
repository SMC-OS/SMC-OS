"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";

import { APP_URL, SITE_NAME, SITE_TAGLINE } from "@/lib/site";

const LINKS = [
  { href: "/#product", label: "Product" },
  { href: "/#trades", label: "Trades" },
  { href: "/#how-it-works", label: "How It Works" },
  { href: "/pricing", label: "Pricing" },
  { href: "/request-demo", label: "Request Demo" },
];

export function Nav() {
  const [open, setOpen] = useState(false);

  return (
    <header className="site-header">
      <div className="shell nav-shell">
        <Link className="wordmark" href="/">
          <span className="wordmark__desktop">
            <Image
              className="wordmark__desktop-mark"
              src="/brand/g-mark.png"
              alt=""
              width={56}
              height={56}
              priority
              quality={100}
            />
            <span className="wordmark__name">{SITE_NAME}</span>
            <span className="sr-only">{`, ${SITE_TAGLINE}`}</span>
          </span>
          <Image
            className="wordmark__mobile"
            src="/brand/g-mark.png"
            alt="GeoCore"
            width={56}
            height={56}
            priority
            quality={100}
          />
        </Link>

        <button
          type="button"
          className="nav-toggle"
          aria-expanded={open}
          aria-controls="primary-nav"
          onClick={() => setOpen((value) => !value)}
        >
          <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
          <span aria-hidden="true">{open ? "✕" : "☰"}</span>
        </button>

        <nav id="primary-nav" className={`nav-links ${open ? "nav-links--open" : ""}`}>
          {LINKS.map((link) => (
            <a key={link.href} href={link.href} onClick={() => setOpen(false)}>
              {link.label}
            </a>
          ))}
          <a className="nav-links__signin" href={`${APP_URL}/login`}>
            Sign in
          </a>
          <a className="button button--primary nav-links__cta" href="/pricing">
            Start Free Trial
          </a>
        </nav>
      </div>
    </header>
  );
}

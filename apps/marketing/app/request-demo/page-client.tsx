"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { ApiError, submitDemoRequest } from "@/lib/api";
import { CONTACT_METHOD_OPTIONS, TEAM_SIZE_OPTIONS, TRADES } from "@/lib/trades";

interface FormState {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  company_name: string;
  team_size: string;
  trades: string[];
  current_system: string;
  message: string;
  preferred_contact_method: string;
  website: string; // honeypot
}

const INITIAL_STATE: FormState = {
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  company_name: "",
  team_size: "",
  trades: [],
  current_system: "",
  message: "",
  preferred_contact_method: "",
  website: "",
};

export function RequestDemoPageClient() {
  const [form, setForm] = useState<FormState>(INITIAL_STATE);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function toggleTrade(key: string) {
    setForm((prev) => ({
      ...prev,
      trades: prev.trades.includes(key)
        ? prev.trades.filter((t) => t !== key)
        : [...prev.trades, key],
    }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!form.first_name.trim() || !form.last_name.trim()) {
      setError("Please enter your first and last name.");
      return;
    }
    if (!form.email.trim()) {
      setError("Please enter your work email.");
      return;
    }
    if (!form.company_name.trim()) {
      setError("Please enter your company name.");
      return;
    }
    if (!form.team_size) {
      setError("Please select your team size.");
      return;
    }
    if (form.trades.length === 0) {
      setError("Please select at least one trade.");
      return;
    }

    setSubmitting(true);
    try {
      await submitDemoRequest({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim() || undefined,
        company_name: form.company_name.trim(),
        team_size: form.team_size,
        trades: form.trades,
        current_system: form.current_system.trim() || undefined,
        message: form.message.trim() || undefined,
        preferred_contact_method: form.preferred_contact_method || undefined,
        website: form.website,
      });
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <>
        <Nav />
        <main>
          <section className="section section--tight">
            <div className="shell demo-success">
              <p className="eyebrow">Request received</p>
              <h1>Demo request received.</h1>
              <p className="section__lead">
                We&apos;ll contact you using the details you provided.
              </p>
              <div className="actions">
                <Link className="button button--primary" href="/">
                  Explore GeoCore
                </Link>
                <Link className="button button--secondary" href="/pricing">
                  View Pricing
                </Link>
              </div>
            </div>
          </section>
        </main>
        <Footer />
      </>
    );
  }

  return (
    <>
      <Nav />
      <main>
        <section className="section section--tight">
          <div className="shell">
            <p className="eyebrow">Request a Demo</p>
            <h1>See GeoCore run your own kind of job</h1>
            <p className="section__lead">
              Tell us about your business and we&apos;ll get in touch — no account and no card
              required.
            </p>
          </div>
        </section>

        <section className="section">
          <div className="shell shell--narrow">
            <form className="demo-form" onSubmit={handleSubmit} noValidate>
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}

              <div className="form-row">
                <label>
                  First name
                  <input
                    type="text"
                    required
                    value={form.first_name}
                    onChange={(e) => update("first_name", e.target.value)}
                    autoComplete="given-name"
                  />
                </label>
                <label>
                  Last name
                  <input
                    type="text"
                    required
                    value={form.last_name}
                    onChange={(e) => update("last_name", e.target.value)}
                    autoComplete="family-name"
                  />
                </label>
              </div>

              <div className="form-row">
                <label>
                  Work email
                  <input
                    type="email"
                    required
                    value={form.email}
                    onChange={(e) => update("email", e.target.value)}
                    autoComplete="email"
                  />
                </label>
                <label>
                  Phone number <span className="optional">(optional)</span>
                  <input
                    type="tel"
                    value={form.phone}
                    onChange={(e) => update("phone", e.target.value)}
                    autoComplete="tel"
                  />
                </label>
              </div>

              <label>
                Company name
                <input
                  type="text"
                  required
                  value={form.company_name}
                  onChange={(e) => update("company_name", e.target.value)}
                  autoComplete="organization"
                />
              </label>

              <label>
                Team size
                <select
                  required
                  value={form.team_size}
                  onChange={(e) => update("team_size", e.target.value)}
                >
                  <option value="" disabled>
                    Select team size
                  </option>
                  {TEAM_SIZE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <fieldset className="trade-fieldset">
                <legend>Primary trade(s)</legend>
                <div className="trade-checkboxes">
                  {TRADES.map((trade) => (
                    <label key={trade.key} className="trade-checkbox">
                      <input
                        type="checkbox"
                        checked={form.trades.includes(trade.key)}
                        onChange={() => toggleTrade(trade.key)}
                      />
                      {trade.label}
                    </label>
                  ))}
                </div>
              </fieldset>

              <label>
                Current software / process <span className="optional">(optional)</span>
                <input
                  type="text"
                  value={form.current_system}
                  onChange={(e) => update("current_system", e.target.value)}
                />
              </label>

              <label>
                What do you want GeoCore to help with? <span className="optional">(optional)</span>
                <textarea
                  rows={4}
                  value={form.message}
                  onChange={(e) => update("message", e.target.value)}
                />
              </label>

              <fieldset>
                <legend>Preferred contact method <span className="optional">(optional)</span></legend>
                <div className="radio-row">
                  {CONTACT_METHOD_OPTIONS.map((option) => (
                    <label key={option.value} className="radio-option">
                      <input
                        type="radio"
                        name="preferred_contact_method"
                        checked={form.preferred_contact_method === option.value}
                        onChange={() => update("preferred_contact_method", option.value)}
                      />
                      {option.label}
                    </label>
                  ))}
                </div>
              </fieldset>

              {/* Honeypot — hidden from real visitors via CSS, never via
                  `type="hidden"` (some bots skip those). */}
              <label className="honeypot" aria-hidden="true">
                Website
                <input
                  type="text"
                  tabIndex={-1}
                  autoComplete="off"
                  value={form.website}
                  onChange={(e) => update("website", e.target.value)}
                />
              </label>

              <button type="submit" className="button button--primary" disabled={submitting}>
                {submitting ? "Sending…" : "Request a Demo"}
              </button>
            </form>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}

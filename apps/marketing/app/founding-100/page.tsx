import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { Footer } from "@/components/Footer";
import { TRIAL_DAYS } from "@/lib/pricing";
import { APP_URL, SEO_LONG_NAME, SEO_NAME, SITE_NAME, SITE_URL } from "@/lib/site";

import { Faq, type FaqItem } from "../start/faq";
import { TrackedAnchor, TrackedLink } from "../start/start-client";
import { FoundingTracker } from "./founding-client";

// /founding-100 is the organic, indexable front door of the Founding 100
// campaign (unlike /start, which is a noindex paid-ad funnel). It is listed
// in app/sitemap.ts and its canonical is the shared SITE_URL host.
const CANONICAL = `${SITE_URL}/founding-100`;

const TITLE = "Join the Founding 100: stone & construction business software";
const DESCRIPTION = `GeoCore OS is stone and construction business software: enquiries, quotes, customers, materials, projects, documents and your team in one system. Join the Founding 100: first 100 businesses, ${TRIAL_DAYS}-day trial, no card required, personal founder onboarding.`;

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: CANONICAL },
  // A page-level openGraph replaces the layout's whole object, so everything a
  // social preview needs is stated here.
  openGraph: {
    type: "website",
    url: CANONICAL,
    siteName: SEO_NAME,
    title: `Join the Founding 100 | ${SEO_LONG_NAME}`,
    description: DESCRIPTION,
    locale: "en_GB",
    images: [`${SITE_URL}/brand/og-image.png`],
  },
  twitter: {
    card: "summary_large_image",
    title: `Join the Founding 100 | ${SEO_LONG_NAME}`,
    description: DESCRIPTION,
    images: [`${SITE_URL}/brand/og-image.png`],
  },
};

const SIGNUP_URL = `${APP_URL}/signup`;
const LOGIN_URL = `${APP_URL}/login`;
const DEMO_URL = "/request-demo";
const EVENT_PROPS = { page: "/founding-100" };

const WORKFLOW = [
  "Enquiry",
  "Quote",
  "Customer",
  "Material",
  "Project",
  "Documents & Photos",
  "Team",
  "Follow-up",
];

const WHO = [
  "Stone fabricators",
  "Quartz, marble and granite companies",
  "Worktop suppliers",
  "Worktop installers",
  "Stone contractors",
  "Construction companies and contractors",
];

const PROBLEMS = [
  "Enquiries arrive on WhatsApp, by email and by phone, and get lost between them.",
  "Quotes live in spreadsheets, so every one is built a little differently.",
  "Job photos sit on someone's phone and documents sit in folders nobody can find.",
  "Customer details are scattered, so the team keeps asking each other what was agreed.",
];

const SOLUTIONS = [
  {
    title: "One customer record",
    body: "Enquiries, customers and the conversation history stay together instead of across five tools.",
  },
  {
    title: "Quotes built for the trade",
    body: "Quote with real material and slab calculations, priced consistently every time.",
  },
  {
    title: "Materials and projects connected",
    body: "An approved quote becomes a project, with the materials, tasks and schedule attached.",
  },
  {
    title: "Documents and photos kept with the job",
    body: "Upload documents and job photos against the customer, so they are never in the wrong place.",
  },
  {
    title: "Your team on the same page",
    body: "Everyone from the office to site works from the same record, with roles and permissions.",
  },
  {
    title: "Follow-up that does not slip",
    body: "Stale enquiries and open jobs are flagged, so the next step is not left to memory.",
  },
];

// The approved Founding 100 offer, verbatim in substance. Nothing here may be
// reworded into a stronger promise: no lifetime access, no lifetime discount,
// no automatic billing, no scarcity counter.
const MEMBER_BENEFITS = [
  "The first 100 businesses",
  `A ${TRIAL_DAYS}-day trial, with no card required`,
  "Personal founder onboarding",
  "Assisted initial setup and import",
  "Direct access to the founder",
  "Influence over the roadmap",
  "Early access to new capabilities",
  "Permanent Founding 100 recognition",
  "Launch-price protection for 24 months",
];

const STEPS = [
  {
    title: "Start the trial",
    body: `Join the Founding 100 and start your ${TRIAL_DAYS}-day trial. No card is needed.`,
  },
  {
    title: "Set up the business",
    body: "Add your company and team. The founder helps with your initial setup and import.",
  },
  {
    title: "Bring in your first customer or job",
    body: "Start with a real enquiry, customer or project so you see it working on your own work.",
  },
  {
    title: "Run the workflow through GeoCore OS",
    body: "Quote, track the project, keep documents and photos with it, and follow up, all in one place.",
  },
];

const FAQ_ITEMS: FaqItem[] = [
  {
    question: "What is the Founding 100?",
    answer:
      "The Founding 100 is the first 100 businesses to join GeoCore OS. Members get personal founder onboarding, assisted initial setup and import, direct access to the founder, a say in the roadmap, early access to new capabilities, permanent Founding 100 recognition and launch-price protection for 24 months.",
  },
  {
    question: "Do I need a credit card to join?",
    answer: `No. The ${TRIAL_DAYS}-day trial needs no card. Nothing is charged when it ends. You only add payment details if you choose a plan.`,
  },
  {
    question: "What happens after the trial?",
    answer:
      "Your trial ends on its own and nothing is billed automatically, because no payment details are held. To carry on, you choose a plan and add your payment details yourself. Your data stays in your workspace.",
  },
  {
    question: "Who is GeoCore OS for?",
    answer:
      "It is built first for stone businesses such as fabricators, worktop companies and installers, and for the construction companies and contractors that run on enquiries, quotes and projects.",
  },
  {
    question: "Can I see it before I join?",
    answer:
      "Yes. You can book a demo and the founder will show you the workflow from enquiry to project.",
  },
];

export default function Founding100Page() {
  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebPage",
        "@id": `${CANONICAL}#webpage`,
        url: CANONICAL,
        name: TITLE,
        description: DESCRIPTION,
        inLanguage: "en-GB",
        isPartOf: { "@id": `${SITE_URL}/#website` },
        about: {
          "@type": "SoftwareApplication",
          name: SEO_NAME,
          alternateName: SEO_LONG_NAME,
          applicationCategory: "BusinessApplication",
          operatingSystem: "Web",
        },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: SEO_NAME, item: SITE_URL },
          { "@type": "ListItem", position: 2, name: "Founding 100", item: CANONICAL },
        ],
      },
    ],
  };

  return (
    <div className="start-page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />
      <FoundingTracker />

      <header className="site-header start-header">
        <div className="shell start-header__inner">
          <Link className="wordmark start-header__brand" href="/">
            <Image
              src="/brand/g-mark.png"
              alt={`${SEO_NAME}, back to the main site`}
              width={116}
              height={116}
              priority
            />
            <span className="start-header__name">{SITE_NAME}</span>
          </Link>
          <nav className="start-header__nav" aria-label="Account">
            <TrackedAnchor
              className="start-header__login"
              href={LOGIN_URL}
              event="login_clicked"
              eventProps={{ ...EVENT_PROPS, placement: "header" }}
            >
              Log in
            </TrackedAnchor>
            <TrackedLink
              className="button button--primary start-header__cta"
              href={SIGNUP_URL}
              event="founding_join_clicked"
              eventProps={{ ...EVENT_PROPS, placement: "header" }}
            >
              Join the Founding 100
            </TrackedLink>
          </nav>
        </div>
      </header>

      <main>
        {/* 1. Hero */}
        <section className="start-hero" id="founding-hero">
          <div className="shell">
            <p className="eyebrow">{SEO_NAME} &middot; Founding 100</p>
            <h1>Run your stone &amp; construction business on one system.</h1>
            <p className="start-hero__lead">
              Enquiries, customers, quotes, materials, projects, documents,
              photos and your team, connected from start to finish.
            </p>
            <div className="actions">
              <TrackedLink
                className="button button--primary start-hero__cta"
                href={SIGNUP_URL}
                event="founding_join_clicked"
                eventProps={{ ...EVENT_PROPS, placement: "hero" }}
              >
                Join the Founding 100
              </TrackedLink>
              <TrackedAnchor
                className="button button--secondary start-hero__demo"
                href={DEMO_URL}
                event="demo_clicked"
                eventProps={{ ...EVENT_PROPS, placement: "hero" }}
              >
                Book a Demo
              </TrackedAnchor>
            </div>
            <p className="start-reassurance">
              {TRIAL_DAYS}-day trial. No card required.
            </p>

            <ol className="start-steps" aria-label="The GeoCore OS workflow">
              {WORKFLOW.map((step, index) => (
                <li className="start-step" key={step}>
                  <span className="start-step__number">{index + 1}</span>
                  <span className="start-step__label">{step}</span>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* 2. The problem */}
        <section className="section" id="problem">
          <div className="shell">
            <h2>WhatsApp, spreadsheets, email and folders are pulling your operation apart</h2>
            <p className="section__lead">
              Most stone and construction businesses did not choose this
              set-up. It grew one workaround at a time.
            </p>
            <ul className="start-outcomes">
              {PROBLEMS.map((problem) => (
                <li className="start-outcome" key={problem}>
                  {problem}
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 3. The solution */}
        <section className="section" id="solution">
          <div className="shell">
            <h2>GeoCore OS brings the workflow together</h2>
            <p className="section__lead">
              One operating system from enquiry to quote to customer to
              project.
            </p>
            <ul className="grid">
              {SOLUTIONS.map((item) => (
                <li className="card" key={item.title}>
                  <h3>{item.title}</h3>
                  <p>{item.body}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 4. Who it is for */}
        <section className="section" id="who">
          <div className="shell">
            <h2>Built for stone and construction businesses</h2>
            <p className="section__lead">
              Built first for stone businesses, and for the construction
              companies that run on enquiries, quotes and projects.
            </p>
            <ul className="start-chips">
              {WHO.map((who) => (
                <li className="start-chip" key={who}>
                  {who}
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 5. What Founding 100 members get */}
        <section className="section" id="what-you-get">
          <div className="shell">
            <h2>What Founding 100 members get</h2>
            <p className="section__lead">
              The Founding 100 is the first 100 businesses to join. The
              founder onboards you personally.
            </p>
            <ul className="start-outcomes">
              {MEMBER_BENEFITS.map((benefit) => (
                <li className="start-outcome" key={benefit}>
                  {benefit}
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 6. How it works */}
        <section className="section" id="how-it-works">
          <div className="shell">
            <h2>How it works</h2>
            <ol className="start-steps">
              {STEPS.map((step, index) => (
                <li className="start-step" key={step.title}>
                  <span className="start-step__number">{index + 1}</span>
                  <span className="start-step__label">
                    <strong>{step.title}.</strong> {step.body}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* 7. Founder */}
        <section className="section" id="founder">
          <div className="shell">
            <h2>Founder-built from real experience</h2>
            <p className="section__lead">
              {SEO_NAME} was built by someone who has operated a stone and
              construction company. The same mess kept getting in the way:
              enquiries on WhatsApp, quotes in one place, job photos somewhere
              else, customer information everywhere. GeoCore OS puts that
              workflow into one system, and the Founding 100 is how it is
              being opened up, with the founder onboarding the early
              businesses personally.
            </p>
          </div>
        </section>

        {/* FAQ */}
        <section className="section" id="faq">
          <div className="shell">
            <h2>Questions</h2>
            <Faq items={FAQ_ITEMS} />
          </div>
        </section>

        {/* 8. Final CTA */}
        <section className="section" id="join">
          <div className="shell">
            <h2>Become one of the Founding 100</h2>
            <p className="section__lead">
              {TRIAL_DAYS}-day trial. No card required. Nothing is charged
              unless you choose a plan and add payment details yourself.
            </p>
            <div className="actions">
              <TrackedLink
                className="button button--primary"
                href={SIGNUP_URL}
                event="founding_join_clicked"
                eventProps={{ ...EVENT_PROPS, placement: "final" }}
              >
                Join the Founding 100
              </TrackedLink>
              <TrackedAnchor
                className="button button--secondary"
                href={DEMO_URL}
                event="demo_clicked"
                eventProps={{ ...EVENT_PROPS, placement: "final" }}
              >
                Book a Demo
              </TrackedAnchor>
            </div>
            <p className="start-reassurance">
              See <Link href="/pricing">plans and prices</Link> for what
              happens after your trial.
            </p>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}

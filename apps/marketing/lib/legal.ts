export const LEGAL_EFFECTIVE_DATE = "29 September 2026";
export const LEGAL_VERSION = "1.0";

export type LegalSection = { heading: string; paragraphs: string[]; bullets?: string[] };
export type LegalDocument = {
  slug: string;
  title: string;
  summary: string;
  sections: LegalSection[];
};

const contact = "GEOCORE OS LTD (registration in progress), Vincent Gardens, NW2 7RP, United Kingdom";

export const LEGAL_DOCUMENTS: LegalDocument[] = [
  {
    slug: "privacy-policy",
    title: "Privacy Policy",
    summary: "How GeoCore handles personal information when providing its business software.",
    sections: [
      { heading: "Who this policy covers", paragraphs: [`This policy explains how ${contact} ("GeoCore", "we", "us") handles personal information in its UK-first business software, website, demo requests and related communications. It is written for organisations and professionals aged 18 or over. GEOCORE OS LTD is intended to be the operating legal entity; its registration is in progress.`, "Customers remain responsible for the information they place in their workspaces and for giving notices or obtaining permissions required for their own use of GeoCore."] },
      { heading: "Information we process", paragraphs: ["We process account and profile details, workspace and business details, customer records, project and quotation information, documents and photos uploaded by authorised users, support communications, subscription and invoice metadata, and technical/security records.", "We may also process demo or contact-request details, marketing preferences and consent/source records, campaign attribution where consent permits persistent storage, copyright-report information, and information submitted to configured AI features."], bullets: ["Account and access data: names, email addresses, roles, password-derived security data and verification records.", "Workspace data: business, customer, project, quote, document and operational information entered by a customer.", "Commercial and communications data: plan, payment-provider references, invoices, marketing choices, delivery and suppression records.", "Technical data: browser/storage choices, IP- and security-related logs, device and service telemetry needed to operate and protect the service."] },
      { heading: "Why we use information", paragraphs: ["We use information to provide and administer GeoCore, authenticate users, operate workspaces, respond to requests, provide support, maintain security, prevent fraud or abuse, process subscriptions, meet legal obligations and improve our service.", "For optional analytics or marketing technologies, we rely on the choices made through our consent controls where required. Marketing email is separately controlled by marketing preferences and unsubscribe/suppression records. Necessary verification, password, security, invitation, billing and service messages are not marketing messages."] },
      { heading: "Legal bases and rights", paragraphs: ["Where UK data-protection law applies, processing may be necessary for a contract, our legitimate interests in operating and protecting a B2B service, compliance with legal obligations, or consent where that is the appropriate basis. The precise basis can depend on the context and the relationship with the individual.", "Individuals may have rights to request access, correction, deletion, restriction, objection, portability or withdrawal of consent. Workspace owners can use available export and deletion controls; users may contact privacy@geocore.one for help. Individuals may also complain to the UK Information Commissioner's Office. This policy does not state an ICO registration number."] },
      { heading: "Retention, export and deletion", paragraphs: ["Workspace owners can request a tenant-scoped export and request workspace deletion. A deletion request starts a 30-day recovery period during which the owner may cancel it. Final purge is an internal, authorised process and occurs only after eligibility; it is not initiated directly by a workspace owner.", "Ordinary workspace information may be deleted or anonymised after the recovery window. Billing/accounting, security/audit, suppression, deletion/copyright evidence and backup copies can have different retention characteristics where necessary. We do not promise that every category is erased exactly 30 days after a request."] },
      { heading: "Processors, international processing and contact", paragraphs: ["We use service providers to operate the service. The current verified subprocessor information is published in our Subprocessor Information page and may change as services are configured. Provider processing may occur outside the UK; the applicable safeguards and contractual arrangements depend on the provider and circumstances and remain subject to legal review.", "Configured AI features may send the submitted request and information needed for that feature to the configured server-side AI provider. Provider credentials remain server-side. We do not promise a provider's retention, training or processing location unless separately confirmed. Contact privacy@geocore.one with privacy questions."] },
    ],
  },
  {
    slug: "terms-of-service",
    title: "Terms of Service",
    summary: "The business terms for access to and use of GeoCore.",
    sections: [
      { heading: "Agreement and eligibility", paragraphs: [`These Terms govern use of GeoCore, provided by ${contact}. They are intended for business and professional use by people aged 18 or over. By creating an account or using GeoCore, you confirm you have authority to bind the organisation whose workspace you administer.`, "Contractual provisions, including liability, governing law and data-protection allocation, require qualified UK legal review before production publication."] },
      { heading: "Accounts and workspaces", paragraphs: ["You must provide accurate account information, protect credentials, keep access details confidential and promptly notify us of suspected unauthorised use. Workspace owners manage membership and permissions. You are responsible for activity undertaken through authorised accounts and for ensuring your users comply with these Terms and the Acceptable Use Policy.", "GeoCore may verify email addresses and apply reasonable security controls before allowing access to relevant features."] },
      { heading: "Trials, subscriptions and cancellation", paragraphs: ["Eligible new workspaces receive a 14-day free trial without a card. A card is not required to begin that trial. Paid plans, where selected, are presented with their price, billing interval, recurring nature and cancellation route before Checkout.", "Payments and the customer billing portal are provided through configured payment services. You may cancel through the available self-service portal where applicable. We do not state a refund policy here; any future refund position must be expressly adopted and reviewed. Taxes may apply where required."] },
      { heading: "Customer data, uploads and AI", paragraphs: ["You retain responsibility for Customer Data and must have the rights and permissions needed to submit it, including uploaded documents, photos, logos and other content. GeoCore processes Customer Data to provide the service. Authorised users can delete supported files; workspace deletion follows the recoverable process described in our Privacy Policy.", "AI-assisted features may use configured server-side providers to process a submitted request and the information necessary to answer it. AI output can be incomplete or inaccurate and should be reviewed by a qualified person before relying on it. Do not submit information you are not authorised to share."] },
      { heading: "Acceptable use, suspension and termination", paragraphs: ["You must not misuse GeoCore, circumvent security or tenant boundaries, interfere with the service, upload unlawful content or infringe others' rights. We may investigate and reasonably suspend or restrict access to protect users, comply with law, address security risk or enforce these Terms.", "On termination, access may end and Customer Data will be handled under the applicable deletion and retention processes. Service changes may occur as we develop the product; we do not promise uninterrupted availability or a service-level agreement unless separately agreed in writing."] },
      { heading: "Intellectual property, liability and notices", paragraphs: ["GeoCore and its underlying software, branding and materials remain our intellectual property or that of our licensors. These Terms do not transfer ownership. You grant us the limited rights needed to host, process and display Customer Data to provide the service.", "Liability limitations, indemnities, disclaimers, notices, governing law and jurisdiction are subject to professional UK legal review. The intended governing-law position is England and Wales. Notices may be sent through the service or to the contact details associated with an account."] },
    ],
  },
  {
    slug: "cookie-policy",
    title: "Cookie Policy",
    summary: "How browser storage and tracking choices work on GeoCore.",
    sections: [
      { heading: "Our approach", paragraphs: ["GeoCore uses browser storage and related technologies to operate securely and remember choices. We classify storage as essential, preferences, analytics or marketing. We do not treat every item of storage as requiring the same choice.", "Optional analytics and marketing technologies are off unless the appropriate choice is recorded. You can reject optional categories, change preferences later, or revoke optional consent; revocation stops future optional tracking but does not undo processing that has already occurred."] },
      { heading: "Essential and preference storage", paragraphs: ["Essential storage supports authentication, session/security functions, CSRF- or request-related protections where used, and service operation. It cannot be disabled through the optional preference control without affecting core functionality.", "Preference storage records choices such as consent settings, theme or similar user preferences. GeoCore stores a version, source and timestamp for consent choices so the service can apply the selected categories."] },
      { heading: "Analytics, marketing and attribution", paragraphs: ["Analytics is only used where configured and enabled by the relevant choice. GeoCore does not claim to use Google Analytics in this policy.", "Marketing technology, including Meta Pixel when configured, does not initialise, emit PageView or emit custom events before marketing consent. Campaign URL parameters can still function for the immediate visit, but persistent campaign/UTM attribution is consent-aware and is not retained without the appropriate choice."] },
      { heading: "Managing choices", paragraphs: ["Use the Cookie preferences control on the marketing site or Settings > Privacy & communications in the application to review and change browser choices. Marketing email preferences are separate from browser tracking choices and can be changed through the authenticated privacy area or the unsubscribe route in a marketing email.", "Storage duration varies by purpose and configuration. We do not state a universal cookie lifetime."] },
    ],
  },
  {
    slug: "acceptable-use-policy",
    title: "Acceptable Use Policy",
    summary: "Rules that help keep GeoCore secure, lawful and useful for every workspace.",
    sections: [
      { heading: "Prohibited use", paragraphs: ["You must use GeoCore lawfully, professionally and only for purposes you are authorised to pursue. You must not use the service to commit fraud, facilitate unlawful conduct, distribute malware, harass others, infringe intellectual-property rights, or upload content you are not entitled to use."], bullets: ["Attempt to bypass authentication, rate limits, permissions, tenant boundaries or security controls.", "Probe, scan, interfere with or overload infrastructure, or use abusive automation.", "Attempt to obtain another organisation's data, credentials or commercial information.", "Upload malicious files, exploit vulnerabilities, or introduce harmful code.", "Use AI functionality to generate or facilitate harmful, unlawful, deceptive or rights-infringing activity."] },
      { heading: "Enforcement", paragraphs: ["We may investigate apparent misuse and take proportionate steps, including restricting access, removing content where appropriate, preserving evidence, notifying affected parties or authorities where required, and suspending or terminating accounts. These measures do not reduce a customer's responsibility for its users and data."] },
    ],
  },
  {
    slug: "copyright-takedown-policy",
    title: "Copyright / Takedown Policy",
    summary: "How to report alleged copyright infringement involving GeoCore content or uploads.",
    sections: [
      { heading: "Submitting a report", paragraphs: ["Anyone with a good-faith copyright concern may submit a report through GeoCore's copyright-report process or email copyright@geocore.one. Please identify the work, the allegedly infringing material or location, your relationship to the rights, contact details, and a clear explanation of the concern.", "Do not include unnecessary sensitive information. A report is not a grant of administrative access and may be reviewed through GeoCore's internal compliance process."] },
      { heading: "Review and response", paragraphs: ["We review reports in context and may request further information. Where appropriate, we may restrict access to, remove, preserve, or otherwise manage reported material while we assess the issue. We may contact the affected user and allow a response where appropriate.", "GeoCore does not represent that it has a registered US DMCA designated agent and this policy is not presented as a formal US DMCA-agent process."] },
      { heading: "Accuracy and repeat concerns", paragraphs: ["Reports must be accurate and made in good faith. False or misleading reports may lead to rejection or other appropriate action. We may consider repeated, substantiated infringement or abuse when deciding whether to restrict or terminate access, taking account of the circumstances and applicable law."] },
    ],
  },
  {
    slug: "data-processing-agreement",
    title: "Data Processing Agreement",
    summary: "The B2B data-processing framework for Customer Data handled through GeoCore.",
    sections: [
      { heading: "Roles, scope and instructions", paragraphs: ["Where a customer submits personal data to GeoCore for its own business purposes, the customer acts as controller and GeoCore acts as processor for that Customer Data, except where GeoCore acts independently for its own account, security, legal, billing or service-administration purposes. This DPA forms part of the service agreement.", "Processing lasts for the term of the service and any applicable deletion/retention period. It includes hosting, storage, organisation, retrieval, transmission when requested by the customer, support, security, backup and deletion of Customer Data under documented customer instructions and these Terms."] },
      { heading: "Data and people concerned", paragraphs: ["Customer Data can include account users, customers, leads, contacts, supplier or project contacts, and other people whose information a customer uploads or enters. Categories may include identification/contact details, business and project information, quotations, communications, documents/photos and other data selected by the customer.", "Customers must ensure instructions and data are lawful, documented where required, and within the scope of the service."] },
      { heading: "Processor commitments", paragraphs: ["GeoCore will ensure people authorised to process Customer Data are subject to confidentiality obligations, implement appropriate technical and organisational measures, assist reasonably with data-subject requests and security information, and notify the customer of personal-data incidents as required by applicable law.", "GeoCore may use subprocessors to provide the service and will maintain the verified subprocessor information page. Customers may raise reasonable concerns through privacy@geocore.one. Subprocessor, transfer and audit terms require professional UK legal review before production publication."] },
      { heading: "Return, deletion, audits and transfers", paragraphs: ["On termination, Customer Data is handled through the available export and recoverable deletion process, subject to the retention architecture for billing, security, suppression, audit evidence, backup and legal requirements. The 30-day workspace recovery period is not a promise that every category will be erased at the end of that period.", "GeoCore will provide reasonable information needed to demonstrate compliance, subject to security and confidentiality safeguards. International transfers, including any UK GDPR transfer mechanism, depend on provider and customer configuration and are not represented as pre-executed by this DPA."] },
    ],
  },
  {
    slug: "subprocessors",
    title: "Subprocessor Information",
    summary: "Verified providers used or conditionally used to operate GeoCore.",
    sections: [
      { heading: "How to read this list", paragraphs: ["This list describes providers evidenced by GeoCore's implementation or runtime configuration. A conditional provider is only used when the relevant service is configured or feature is invoked. We do not publish unverified geographic processing locations or transfer mechanisms here."] },
      { heading: "Verified service providers", paragraphs: ["Stripe — subscription Checkout, payment processing and customer billing portal; may receive billing/customer details needed for payment services when configured.", "Resend — transactional and marketing email delivery and delivery-event handling; may receive recipient, sender, message and suppression information when configured.", "Railway — application/infrastructure hosting referenced by deployment configuration; may process service, database and log information necessary to operate the hosted service."] },
      { heading: "Conditional providers", paragraphs: ["OpenAI — configured server-side AI functionality; receives the submitted feature request and bounded information necessary to provide that feature.", "Google Gemini — configured server-side AI functionality; receives the submitted feature request and bounded information necessary to provide that feature.", "Meta — marketing measurement only when configured and only after applicable marketing consent; receives event information permitted by the configured implementation and user choice."] },
      { heading: "Not included", paragraphs: ["ElevenLabs is not listed because a dependency alone is not evidence that GeoCore sends it customer data. We will update this page only when a provider is actually configured or used in a way that makes it a relevant subprocessor."] },
    ],
  },
];

export function findLegalDocument(slug: string): LegalDocument | undefined {
  return LEGAL_DOCUMENTS.find((document) => document.slug === slug);
}

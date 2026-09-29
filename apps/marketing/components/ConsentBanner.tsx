"use client";

import { useState } from "react";
import { readConsent, saveConsent } from "@/lib/consent";

export function ConsentBanner() {
  const [visible, setVisible] = useState(() => !readConsent());
  return <>
    {visible && <section className="consent-banner" aria-label="Cookie preferences">
      <p>We use essential storage to run GeoCore. Optional analytics and marketing technologies are off unless you choose them.</p>
      <div><button type="button" onClick={() => { saveConsent({ preferences: false, analytics: false, marketing: false }, "banner"); setVisible(false); }}>Use essential only</button>
      <button type="button" onClick={() => { saveConsent({ preferences: true, analytics: true, marketing: true }, "banner"); setVisible(false); }}>Accept optional technologies</button></div>
    </section>}
    {!visible && <button className="consent-manage" type="button" onClick={() => setVisible(true)}>Cookie preferences</button>}
  </>;
}

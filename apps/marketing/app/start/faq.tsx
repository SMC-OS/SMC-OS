"use client";

import { useState } from "react";

import { track } from "./tracker";

export type FaqItem = {
  question: string;
  answer: string;
};

/** Accessible accordion for the /start FAQ. Tracks first open per item. */
export function Faq({ items }: { items: FaqItem[] }) {
  const [open, setOpen] = useState<number | null>(null);

  return (
    <div className="start-faq">
      {items.map((item, index) => {
        const isOpen = open === index;
        return (
          <div className="start-faq__item" key={item.question}>
            <h3 className="start-faq__heading">
              <button
                type="button"
                className="start-faq__button"
                aria-expanded={isOpen}
                aria-controls={`start-faq-panel-${index}`}
                onClick={() => {
                  if (!isOpen) track("faq_opened", { question_index: index });
                  setOpen(isOpen ? null : index);
                }}
              >
                <span>{item.question}</span>
                <span className="start-faq__icon" aria-hidden="true">
                  {isOpen ? "−" : "+"}
                </span>
              </button>
            </h3>
            <div
              id={`start-faq-panel-${index}`}
              className="start-faq__panel"
              hidden={!isOpen}
            >
              <p>{item.answer}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

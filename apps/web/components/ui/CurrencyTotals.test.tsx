import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { CurrencyTotals } from "./CurrencyTotals";
afterEach(cleanup);
it("shows independent currencies rather than a fabricated combined amount", () => {
  render(<CurrencyTotals amounts={{ GBP: 100, EUR: 200, USD: 0.02 }} value={300.02} currency="EUR" />);
  expect(screen.getByText("£100")).toBeInTheDocument();
  expect(screen.getByText("€200")).toBeInTheDocument();
  expect(screen.getByText("US$0.02")).toBeInTheDocument();
  expect(screen.queryByText("€300.02")).not.toBeInTheDocument();
});
it("preserves non-zero pennies and handles empty workspace totals", () => {
  const view = render(<CurrencyTotals amounts={{ GBP: 0.02 }} value={0.02} />);
  expect(screen.getByText("£0.02")).toBeInTheDocument();
  view.rerender(<CurrencyTotals amounts={{}} value={0} currency="EUR" />);
  expect(screen.getByText("€0")).toBeInTheDocument();
});

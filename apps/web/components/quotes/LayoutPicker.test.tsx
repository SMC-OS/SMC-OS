import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { LayoutPicker } from "./LayoutPicker";

afterEach(cleanup);

it("offers the eight reference layouts and a large labelled plan", async () => {
  const onChange = vi.fn();
  render(<LayoutPicker value="l_shape" onChange={onChange} idPrefix="quote" />);
  const picker = screen.getByRole("combobox", { name: "Worktop layout" });
  expect(screen.getAllByRole("option")).toHaveLength(10); // prompt, eight layouts, legacy peninsula
  expect(
    screen.getByRole("img", { name: /L-shape.*pieces A, B/i }),
  ).toBeInTheDocument();
  await userEvent.selectOptions(picker, "u_shape_island");
  expect(onChange).toHaveBeenCalledWith("u_shape_island");
});

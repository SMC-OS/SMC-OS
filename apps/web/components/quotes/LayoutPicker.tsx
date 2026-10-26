"use client";

import { Field, Select } from "@/components/ui/Field";
import {
  LAYOUT_LABELS,
  LAYOUT_OPTIONS,
  type LayoutOption,
} from "@/types/quote";

export type WorktopPiece = { label: string; length: string; width: string };
type PlanPiece = {
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
  island?: boolean;
};

const top: PlanPiece = { label: "A", x: 35, y: 35, w: 330, h: 65 };
const left: PlanPiece = { label: "B", x: 35, y: 102, w: 65, h: 170 };
const right: PlanPiece = { label: "C", x: 300, y: 102, w: 65, h: 170 };
const centre = (label: string): PlanPiece => ({
  label,
  x: 155,
  y: 155,
  w: 95,
  h: 85,
  island: true,
});

// Original vector plans with the reference's labelled-piece convention.
// These are schematic layouts, not a fabrication or slab-nesting drawing.
export function planPieces(layout: LayoutOption): PlanPiece[] {
  switch (layout) {
    case "straight":
      return [top];
    case "l_shape":
      return [top, left];
    case "l_shape_island":
      return [top, left, centre("C")];
    case "u_shape":
      return [top, left, right];
    case "u_shape_island":
      return [top, left, right, centre("D")];
    case "island":
      return [top, centre("B")];
    case "galley":
      return [top, { label: "B", x: 35, y: 205, w: 330, h: 65 }];
    case "galley_island":
      return [
        top,
        { label: "B", x: 35, y: 230, w: 330, h: 65 },
        { label: "C", x: 155, y: 130, w: 95, h: 65, island: true },
      ];
    case "peninsula":
      return [top, { label: "B", x: 170, y: 102, w: 65, h: 170 }];
  }
}

export function WorktopPlan({ layout }: { layout: LayoutOption }) {
  const pieces = planPieces(layout);
  return (
    <figure className="mt-5 overflow-hidden rounded-xl border border-border bg-background">
      <svg
        viewBox="0 0 400 330"
        role="img"
        aria-label={`${LAYOUT_LABELS[layout]} worktop plan, pieces ${pieces.map((p) => p.label).join(", ")}`}
        className="mx-auto block w-full max-w-lg text-foreground"
      >
        <title>{LAYOUT_LABELS[layout]} worktop layout</title>
        {pieces.map((piece) => (
          <g key={piece.label}>
            <rect
              x={piece.x}
              y={piece.y}
              width={piece.w}
              height={piece.h}
              fill="currentColor"
              rx="2"
            />
            <text
              x={piece.x + piece.w / 2}
              y={piece.y + piece.h / 2}
              textAnchor="middle"
              dominantBaseline="central"
              fill="var(--background)"
              fontSize="24"
              fontWeight="600"
            >
              {piece.label}
            </text>
          </g>
        ))}
      </svg>
      <figcaption className="border-t border-border px-4 py-3 text-sm text-muted">
        {LAYOUT_LABELS[layout]} · {pieces.length} pieces · schematic, not to
        scale
      </figcaption>
    </figure>
  );
}

export function LayoutPicker({
  value,
  onChange,
  idPrefix,
}: {
  value: LayoutOption | "";
  onChange: (value: LayoutOption | "") => void;
  idPrefix: string;
}) {
  return (
    <div>
      <Field label="Worktop layout" htmlFor={`${idPrefix}-layout`}>
        <Select
          id={`${idPrefix}-layout`}
          value={value}
          onChange={(event) =>
            onChange(event.target.value as LayoutOption | "")
          }
        >
          <option value="">Individual piece / custom layout</option>
          {LAYOUT_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option === "straight"
                ? "One piece"
                : option === "island"
                  ? "One piece + island"
                  : LAYOUT_LABELS[option]}
            </option>
          ))}
        </Select>
      </Field>
      {value && <WorktopPlan layout={value} />}
    </div>
  );
}

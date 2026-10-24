"use client";

import { EXTRA_LABELS, EXTRA_OPTIONS, type ExtraOption } from "@/types/quote";
import { Field, Input, Select } from "@/components/ui/Field";
import { cn } from "@/lib/utils";

export type DesignDetails = {
  edgeProfile: string;
  customEdgeProfile: string;
  sink: string;
  hob: string;
  taps: string;
  upstandLength: string;
  upstandHeight: string;
  splashbackLength: string;
  splashbackHeight: string;
};
export const blankDesignDetails = (): DesignDetails => ({
  edgeProfile: "",
  customEdgeProfile: "",
  sink: "",
  hob: "",
  taps: "",
  upstandLength: "",
  upstandHeight: "",
  splashbackLength: "",
  splashbackHeight: "",
});

export function ExtrasPicker({
  value,
  onChange,
  idPrefix,
  details,
  onDetailsChange,
}: {
  value: ExtraOption[];
  onChange: (value: ExtraOption[]) => void;
  idPrefix: string;
  details: DesignDetails;
  onDetailsChange: (details: DesignDetails) => void;
}) {
  const update = (key: keyof DesignDetails, next: string) =>
    onDetailsChange({ ...details, [key]: next });
  return (
    <div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {EXTRA_OPTIONS.map((option) => (
          <label
            key={option}
            className={cn(
              "flex min-h-14 cursor-pointer items-center gap-3 rounded-xl border p-4 text-sm font-medium",
              value.includes(option)
                ? "border-accent bg-accent/10 text-accent"
                : "border-border bg-background text-foreground",
            )}
          >
            <input
              id={`${idPrefix}-extra-${option}`}
              type="checkbox"
              className="h-5 w-5 accent-[var(--accent)]"
              checked={value.includes(option)}
              onChange={() =>
                onChange(
                  value.includes(option)
                    ? value.filter((v) => v !== option)
                    : [...value, option],
                )
              }
            />
            {EXTRA_LABELS[option]}
          </label>
        ))}
      </div>
      {value.includes("polished_edge") && (
        <fieldset className="mt-4 rounded-xl border border-border p-4">
          <legend className="px-2 font-semibold">Polished edges</legend>
          <Field
            label="Polished edge profile"
            htmlFor={`${idPrefix}-edge-profile`}
          >
            <Select
              id={`${idPrefix}-edge-profile`}
              value={details.edgeProfile}
              onChange={(e) => update("edgeProfile", e.target.value)}
            >
              <option value="">Select an edge profile</option>
              {[
                "Full bullnose",
                "Half bullnose",
                "Pencil round",
                "Ogee",
                "Double ogee",
                "Eased / square",
                "Bevel",
                "Double bevel",
                "Double bullnose",
                "Mitred",
                "Shark nose",
                "Other / custom",
              ].map((profile) => (
                <option key={profile}>{profile}</option>
              ))}
            </Select>
          </Field>
          {details.edgeProfile === "Other / custom" && (
            <Field
              className="mt-3"
              label="Custom edge profile"
              htmlFor={`${idPrefix}-custom-edge`}
            >
              <Input
                id={`${idPrefix}-custom-edge`}
                value={details.customEdgeProfile}
                onChange={(e) => update("customEdgeProfile", e.target.value)}
                placeholder="Describe the edge required"
              />
            </Field>
          )}
          <p className="mt-3 text-sm text-muted">
            The selected profile is saved on the quote. Confirm fabrication
            suitability and pricing before issuing.
          </p>
        </fieldset>
      )}
      {value.includes("cutout") && (
        <fieldset className="mt-4 rounded-xl border border-border p-4">
          <legend className="px-2 font-semibold">
            Cut-outs &amp; tap holes
          </legend>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Sink mounting" htmlFor={`${idPrefix}-sink`}>
              <Select
                id={`${idPrefix}-sink`}
                value={details.sink}
                onChange={(e) => update("sink", e.target.value)}
              >
                <option value="">No sink cut-out</option>
                {["Overmount", "Flushmount", "Undermount"].map((type) => (
                  <option key={type}>{type}</option>
                ))}
              </Select>
            </Field>
            <Field label="Hob cut-outs" htmlFor={`${idPrefix}-hob`}>
              <Input
                id={`${idPrefix}-hob`}
                type="number"
                min="0"
                step="1"
                value={details.hob}
                onChange={(e) => update("hob", e.target.value)}
                placeholder="0"
              />
            </Field>
            <Field label="Tap holes" htmlFor={`${idPrefix}-taps`}>
              <Input
                id={`${idPrefix}-taps`}
                type="number"
                min="0"
                step="1"
                value={details.taps}
                onChange={(e) => update("taps", e.target.value)}
                placeholder="0"
              />
            </Field>
          </div>
          <p className="mt-3 text-sm text-muted">
            Cut-out and tap-hole requirements are recorded for review. No
            fabrication charge is added automatically.
          </p>
        </fieldset>
      )}
      {(["upstand"] as const).map((kind) => {
        const selected = value.includes("upstand_included");
        if (!selected) return null;
        const title = "Upstand";
        const lengthKey = `${kind}Length` as keyof DesignDetails;
        const heightKey = `${kind}Height` as keyof DesignDetails;
        return (
          <fieldset
            key={kind}
            className="mt-4 rounded-xl border border-border p-4"
          >
            <legend className="px-2 font-semibold">{title}</legend>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field
                label={`${title} length (mm)`}
                htmlFor={`${idPrefix}-${kind}-length`}
              >
                <Input
                  id={`${idPrefix}-${kind}-length`}
                  type="number"
                  min="1"
                  step="1"
                  required
                  value={details[lengthKey]}
                  onChange={(e) => update(lengthKey, e.target.value)}
                />
              </Field>
              <Field
                label={`${title} height (mm)`}
                htmlFor={`${idPrefix}-${kind}-height`}
              >
                <Input
                  id={`${idPrefix}-${kind}-height`}
                  type="number"
                  min="1"
                  step="1"
                  required
                  value={details[heightKey]}
                  onChange={(e) => update(heightKey, e.target.value)}
                />
              </Field>
            </div>
            <p className="mt-3 text-sm text-muted">
              Adds a measured {kind} line using this item’s material, thickness
              and quantity.
            </p>
          </fieldset>
        );
      })}
    </div>
  );
}

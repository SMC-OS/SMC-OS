/**
 * Sprint 034 — the tenant company identity form.
 *
 * Two properties are worth locking down here, because both are the kind of
 * thing a later refactor breaks silently:
 *
 *  1. A save sends only the fields that actually changed. The API applies
 *     PATCH semantics, so sending the whole form would let a stale value
 *     in an untouched input overwrite a field someone else just corrected.
 *  2. Nothing on this screen is prefilled with a platform or hardcoded
 *     company name. This form is the tenant's *own* trading identity — the
 *     exact confusion this sprint exists to fix.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getCompanyProfileMock = vi.fn();
const updateCompanyProfileMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      getCompanyProfile: (...args: unknown[]) => getCompanyProfileMock(...args),
      updateCompanyProfile: (...args: unknown[]) => updateCompanyProfileMock(...args),
    },
  };
});

import CompanyIdentityCard from "./CompanyIdentityCard";

function profile(overrides: Record<string, unknown> = {}) {
  return {
    id: "tenant-1",
    name: "Riverside Stoneworks",
    slug: "riverside-stoneworks",
    status: "active",
    created_at: new Date().toISOString(),
    legal_name: "Riverside Stoneworks Ltd",
    trading_name: null,
    address_line1: "1 Quarry Road",
    address_line2: null,
    city: "Leeds",
    postcode: "LS1 1AA",
    country: null,
    contact_email: null,
    contact_phone: null,
    website: null,
    company_number: "12345678",
    vat_number: "GB123456789",
    logo_url: null,
    document_footer: null,
    ...overrides,
  };
}

beforeEach(() => {
  getCompanyProfileMock.mockReset();
  updateCompanyProfileMock.mockReset();
  getCompanyProfileMock.mockResolvedValue(profile());
});

afterEach(() => {
  cleanup();
});

describe("CompanyIdentityCard", () => {
  it("loads_and_shows_the_tenants_own_configured_details", async () => {
    render(<CompanyIdentityCard />);

    await waitFor(() => {
      expect(screen.getByLabelText("Registered company name")).toHaveValue(
        "Riverside Stoneworks Ltd"
      );
    });
    expect(screen.getByLabelText("VAT registration number")).toHaveValue("GB123456789");
  });

  it("never_prefills_a_platform_or_hardcoded_company_name", async () => {
    getCompanyProfileMock.mockResolvedValue(
      profile({ legal_name: null, company_number: null, vat_number: null })
    );
    render(<CompanyIdentityCard />);

    await waitFor(() => {
      expect(screen.getByLabelText("Registered company name")).toHaveValue("");
    });
    // An unconfigured tenant gets empty inputs, not a default identity —
    // no platform brand, and none of the company that used to be
    // hardcoded into every invoice before this sprint.
    expect(screen.getByLabelText("VAT registration number")).toHaveValue("");
    expect(screen.queryByDisplayValue(/Simo Marble/i)).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue(/SIMO OS/i)).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue(/GeoCore/i)).not.toBeInTheDocument();
  });

  it("sends_only_the_fields_that_changed", async () => {
    updateCompanyProfileMock.mockResolvedValue(profile({ city: "Bradford" }));
    render(<CompanyIdentityCard />);

    await waitFor(() => {
      expect(screen.getByLabelText("Town / city")).toHaveValue("Leeds");
    });

    fireEvent.change(screen.getByLabelText("Town / city"), {
      target: { value: "Bradford" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save company details/i }));

    await waitFor(() => {
      expect(updateCompanyProfileMock).toHaveBeenCalledWith({ city: "Bradford" });
    });
  });

  it("does_not_call_the_api_when_nothing_changed", async () => {
    render(<CompanyIdentityCard />);

    await waitFor(() => {
      expect(screen.getByLabelText("Town / city")).toHaveValue("Leeds");
    });

    fireEvent.click(screen.getByRole("button", { name: /save company details/i }));

    await waitFor(() => {
      expect(screen.getByText("Company details saved.")).toBeInTheDocument();
    });
    expect(updateCompanyProfileMock).not.toHaveBeenCalled();
  });

  it("clearing_a_field_sends_an_empty_string_so_it_can_actually_be_cleared", async () => {
    updateCompanyProfileMock.mockResolvedValue(profile({ vat_number: null }));
    render(<CompanyIdentityCard />);

    await waitFor(() => {
      expect(screen.getByLabelText("VAT registration number")).toHaveValue("GB123456789");
    });

    fireEvent.change(screen.getByLabelText("VAT registration number"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save company details/i }));

    await waitFor(() => {
      expect(updateCompanyProfileMock).toHaveBeenCalledWith({ vat_number: "" });
    });
  });

  it("explains_a_403_rather_than_showing_a_generic_error", async () => {
    const { ApiError } = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
    updateCompanyProfileMock.mockRejectedValue(new ApiError("Forbidden", 403));
    render(<CompanyIdentityCard />);

    await waitFor(() => {
      expect(screen.getByLabelText("Town / city")).toHaveValue("Leeds");
    });

    fireEvent.change(screen.getByLabelText("Town / city"), { target: { value: "York" } });
    fireEvent.click(screen.getByRole("button", { name: /save company details/i }));

    await waitFor(() => {
      expect(
        screen.getByText("Only workspace owners can change company details.")
      ).toBeInTheDocument();
    });
  });
});

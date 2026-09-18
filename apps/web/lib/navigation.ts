import {
  BuildingIcon,
  CalendarIcon,
  CreditCardIcon,
  FileTextIcon,
  FolderIcon,
  HomeIcon,
  LayersIcon,
  PaletteIcon,
  BellIcon,
  SettingsIcon,
  ShieldIcon,
  SparklesIcon,
  UsersIcon,
  ZapIcon,
} from "@/components/ui/icons";

export interface NavItem {
  label: string;
  href: string;
  icon: typeof HomeIcon;
  /**
   * Whether this belongs in the phone bottom bar. Sprint 036 (Workstream
   * A): a bottom bar with seven items is a bottom bar nobody can hit. The
   * four highest-frequency areas live there; everything else is one tap
   * away in the drawer.
   */
  primaryOnMobile?: boolean;
}

/**
 * Single source of truth for primary navigation (Sprint 036, Workstream A).
 *
 * The information architecture is the workflow a construction business
 * actually runs, in order:
 *
 *   Dashboard → Customers → Quotes → Projects → Calendar → Automations → GeoCore AI
 *
 * which is the lead-to-aftercare journey the product is organised around.
 * Settings is deliberately not in this list: it is administrative, it is
 * visited rarely, and putting it alongside daily work is what made the
 * previous six-item sidebar read as a list of screens rather than a
 * workflow. It has its own entry point in the profile menu and its own
 * section list below.
 *
 * The sidebar, the tablet rail, the phone drawer, the phone bottom bar
 * and the command palette all read from here, so adding a module makes it
 * navigable and searchable everywhere at once.
 */
export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/", icon: HomeIcon, primaryOnMobile: true },
  { label: "Customers", href: "/customers", icon: UsersIcon, primaryOnMobile: true },
  { label: "Quotes", href: "/quotes", icon: FileTextIcon, primaryOnMobile: true },
  { label: "Catalogue", href: "/catalogue", icon: LayersIcon },
  { label: "Projects", href: "/projects", icon: FolderIcon, primaryOnMobile: true },
  { label: "Calendar", href: "/calendar", icon: CalendarIcon },
  { label: "Automations", href: "/automations", icon: ZapIcon },
  { label: "GeoCore AI", href: "/ai", icon: SparklesIcon },
];

export const MOBILE_PRIMARY_NAV: NavItem[] = NAV_ITEMS.filter(
  (item) => item.primaryOnMobile
);

export interface SettingsSection {
  key: string;
  label: string;
  description: string;
  icon: typeof HomeIcon;
  /** Owner-only sections are hidden from Staff rather than shown disabled. */
  ownerOnly?: boolean;
}

/**
 * Settings V2 (Workstream I). The previous Settings page was one
 * 483-line scroll containing company identity, team, billing and
 * invitations stacked on top of each other. These are the sections it
 * becomes — administrative concerns, grouped by what a person came to do.
 */
export const SETTINGS_SECTIONS: SettingsSection[] = [
  {
    key: "company",
    label: "Company",
    description: "Trading details, registered address and VAT.",
    icon: BuildingIcon,
    ownerOnly: true,
  },
  {
    key: "branding",
    label: "Branding",
    description: "Your logo and how your documents look.",
    icon: PaletteIcon,
    ownerOnly: true,
  },
  {
    key: "team",
    label: "Team & permissions",
    description: "Members, roles and invitations.",
    icon: UsersIcon,
    ownerOnly: true,
  },
  {
    key: "billing",
    label: "Billing & subscription",
    description: "Your plan, payment method and invoices.",
    icon: CreditCardIcon,
    ownerOnly: true,
  },
  {
    key: "notifications",
    label: "Notifications",
    description: "What GeoCore tells you about, and where.",
    icon: BellIcon,
  },
  {
    key: "security",
    label: "Security",
    description: "Your account and active session.",
    icon: ShieldIcon,
  },
];

export const SETTINGS_ICON = SettingsIcon;

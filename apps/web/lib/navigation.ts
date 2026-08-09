import {
  BotIcon,
  FileTextIcon,
  FolderIcon,
  HomeIcon,
  SettingsIcon,
  UsersIcon,
} from "@/components/ui/icons";

export interface NavItem {
  label: string;
  href: string;
  icon: typeof HomeIcon;
}

/**
 * Single source of truth for primary navigation. Sidebar and the
 * command palette (global search) both read from this list, so adding a
 * future module here is enough to make it navigable and searchable
 * everywhere at once.
 */
export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/", icon: HomeIcon },
  { label: "Customers", href: "/customers", icon: UsersIcon },
  { label: "Quotes", href: "/quotes", icon: FileTextIcon },
  { label: "Projects", href: "/projects", icon: FolderIcon },
  { label: "AI Assistant", href: "/ai-assistant", icon: BotIcon },
  { label: "Settings", href: "/settings", icon: SettingsIcon },
];

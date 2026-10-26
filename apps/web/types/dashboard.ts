export interface DashboardStats {
  quotes_today: number;
  currency?: string;
  quoted_value_by_currency?: Record<string, number>;
  quoted_value: number;
  customers: number;
  projects: number;
}

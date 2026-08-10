export interface CustomerCreate {
  name: string;
  email?: string | null;
  phone?: string | null;
}

export interface Customer extends CustomerCreate {
  id: string;
  created_at: string;
}

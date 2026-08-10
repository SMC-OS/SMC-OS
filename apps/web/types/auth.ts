export interface AuthUser {
  id: string;
  name: string;
  email: string;
  role: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

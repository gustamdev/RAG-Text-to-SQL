// Espelho dos schemas Pydantic de auth do backend (app/schemas/auth.py).

export type Role = string

export interface User {
  id: string
  name: string
  email: string
  role: Role
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export interface LoginInput {
  email: string
  password: string
}

// Espelho do contrato docs/api-loja.md. Dinheiro sempre em centavos de BRL.

export interface Customer {
  id: string
  nickname: string | null
  email: string
  phone?: string | null
  terms_version: string
  created_at: string
}

export interface ProductCard {
  product_id: string
  title: string
  category: string
  category_label: string
  price_cents: number
  stock: number
  avg_rating: number | null
  review_count: number
  units_sold: number
  photos_qty: number | null
  image_url?: string | null
}

export interface ProductDetail extends ProductCard {
  weight_g: number | null
  length_cm: number | null
  height_cm: number | null
  width_cm: number | null
  rating_distribution?: Record<string, number>
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface CategoryOut {
  category: string
  label: string
  product_count: number
}

export interface Suggestions {
  products: ProductCard[]
  categories: { category: string; label: string }[]
}

export type FreightCode = 'standard' | 'economy'

export interface FreightOption {
  code: FreightCode
  label: string
  price_cents: number
  days_min: number
  days_max: number
}

export interface FreightResult {
  zip: string
  options: FreightOption[]
}

export type CartWarning = 'stock_reduced' | 'out_of_stock' | 'price_changed' | null

export interface CartLine {
  product_id: string
  title: string
  category: string
  unit_price_cents: number
  qty: number
  line_total_cents: number
  stock: number
  warning: CartWarning
}

export interface Cart {
  items: CartLine[]
  item_count: number
  subtotal_cents: number
  blocked: boolean
  updated_at?: string
}

export interface Address {
  id: string
  label: string
  recipient: string
  zip: string
  street: string
  number: string
  complement: string | null
  district: string
  city: string
  state: string
  is_default: boolean
}

export type AddressInput = Omit<Address, 'id'>

export interface SavedCard { id: string; brand: string; last4: string; exp_month: number; exp_year: number }
export interface CardInput { card_number: string; holder: string; exp_month: number; exp_year: number; cvv: string }
/** Cartão novo (com opção de salvar) ou cartão salvo + CVV. */
export type PayInput = (CardInput & { save_card: boolean }) | { saved_card_id: string; cvv: string }

export type OrderState = 'created' | 'paid' | 'refused' | 'shipped' | 'delivered' | 'canceled'

export type CancelReason = 'changed_mind' | 'found_cheaper' | 'wrong_item' | 'delivery_too_long' | 'other'

export interface OrderItem {
  product_id: string
  title: string
  category: string
  qty: number
  unit_price_cents: number
  line_total_cents: number
}

export interface Order {
  order_id: string
  state: OrderState
  items: OrderItem[]
  subtotal_cents: number
  freight_cents: number
  discount_cents: number
  total_cents: number
  shipping: { option: FreightCode; label: string; days_min: number; days_max: number }
  address: Omit<Address, 'id' | 'label' | 'is_default'>
  payment: { status: 'approved' | 'refused' | 'timeout'; brand: string; last4: string } | null
  timeline: { state: OrderState; at: string }[]
  reservation_expires_at: string | null
  created_at: string
  canceled_at?: string | null
  cancel_reason?: CancelReason | null
  refund_cents?: number | null
}

export interface OrderSummary {
  order_id: string
  state: OrderState
  total_cents: number
  item_count: number
  created_at: string
  canceled_at?: string | null
  refund_cents?: number | null
}

export interface AuthSession {
  access_token: string
  token_type: string
  customer: Customer
}

export type ProductSort = 'best_selling' | 'price_asc' | 'price_desc' | 'rating' | 'newest'

export interface ProductFilters {
  q?: string
  category?: string
  min_price_cents?: number
  max_price_cents?: number
  min_rating?: number
  min_reviews?: number
  in_stock?: boolean
  sort?: ProductSort
  page?: number
  page_size?: number
}

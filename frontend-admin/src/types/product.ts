// Espelho dos schemas Pydantic de produtos/backoffice do backend. Valores monetários em reais (number).

export interface ProductSummary {
  product_id: string
  /** Rótulo sintético ("categoria_en · #abc12345"): o dataset Olist não tem nome de produto. */
  label: string
  category: string
  category_en: string
  avg_price: number
  avg_rating: number | null
  review_count: number
  units_sold: number
  photos_qty: number | null
}

export interface ProductPhysical {
  weight_g: number | null
  length_cm: number | null
  height_cm: number | null
  width_cm: number | null
  name_length: number | null
  description_length: number | null
}

export interface ProductDetail extends ProductSummary, ProductPhysical {
  related: ProductSummary[]
}

export interface CategoryOut {
  category: string
  category_en: string
  products: number
  units_sold: number
}

/** `month` no formato "YYYY-MM". */
export interface MonthlyPoint {
  month: string
  revenue: number
  units: number
  orders: number
}

export interface AdminProductRow extends ProductSummary {
  revenue: number
  freight_avg: number
  /** 0–100 */
  bad_review_pct: number | null
  /** 0–100 */
  late_pct: number | null
  sellers: number
  rank: number
}

export interface RatingBucket {
  score: number
  count: number
}

export interface TopSeller {
  seller_id: string
  seller_state: string | null
  units: number
  revenue: number
}

export interface AdminProductDetail extends AdminProductRow, ProductPhysical {
  rating_distribution: RatingBucket[]
  monthly: MonthlyPoint[]
  top_sellers: TopSeller[]
}

export interface AdminCategoryRow {
  category: string
  category_en: string
  products: number
  units_sold: number
  revenue: number
  avg_price: number
  avg_rating: number | null
  bad_review_pct: number | null
  late_pct: number | null
  rank: number
}

export interface Kpis {
  revenue: number
  units: number
  orders: number
  avg_ticket: number
  avg_rating: number | null
  late_pct: number | null
  products: number
  sellers: number
  categories: number
}

export interface Overview {
  kpis: Kpis
  monthly: MonthlyPoint[]
  top_categories: AdminCategoryRow[]
  top_products: AdminProductRow[]
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export type ProductSort = 'units' | 'rating' | 'price_asc' | 'price_desc'
export type AdminProductSort = 'units' | 'revenue' | 'rating' | 'price' | 'bad_review_pct' | 'late_pct'
export type SortOrder = 'asc' | 'desc'

export interface ProductFilters {
  q?: string
  category?: string
  sort?: ProductSort
  page?: number
  page_size?: number
}

export interface AdminProductFilters {
  q?: string
  category?: string
  min_rating?: number
  sort?: AdminProductSort
  order?: SortOrder
  page?: number
  page_size?: number
}

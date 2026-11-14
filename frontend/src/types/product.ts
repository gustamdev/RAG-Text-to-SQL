// Espelho dos schemas Pydantic de produtos do backend. Valores monetários em reais (number).

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

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export type ProductSort = 'units' | 'rating' | 'price_asc' | 'price_desc'

export interface ProductFilters {
  q?: string
  category?: string
  sort?: ProductSort
  page?: number
  page_size?: number
}

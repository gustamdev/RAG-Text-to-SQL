import {
  Armchair,
  Baby,
  BedDouble,
  BookOpen,
  Car,
  CookingPot,
  Dumbbell,
  Flower2,
  Gamepad2,
  Gift,
  Hammer,
  Headphones,
  Laptop,
  Luggage,
  Music,
  Package,
  Palette,
  PawPrint,
  PencilRuler,
  Refrigerator,
  Shirt,
  Smartphone,
  Sparkles,
  ToyBrick,
  Tv,
  Watch,
  Wine,
  type LucideIcon,
} from 'lucide-react'

// Ordem importa: a primeira palavra-chave que aparecer no nome da categoria vence.
// Casa tanto nomes em português ("cama_mesa_banho") quanto em inglês ("bed_bath_table").
const RULES: ReadonlyArray<readonly [LucideIcon, readonly string[]]> = [
  [BedDouble, ['cama', 'bed_bath', 'bed']],
  [Sparkles, ['beleza', 'perfum', 'beauty', 'health']],
  [Laptop, ['informatica', 'computer', 'pc_gamer', 'tablets']],
  [Smartphone, ['telefon', 'phone', 'celular']],
  [Gamepad2, ['games', 'console']],
  [Headphones, ['audio']],
  [Music, ['music', 'musica', 'cds_dvds', 'instrumentos']],
  [Tv, ['eletronic', 'electronic', 'tv', 'imagem']],
  [Refrigerator, ['eletrodomest', 'eletroport', 'small_appliances', 'home_appliances', 'portateis']],
  [Dumbbell, ['esporte', 'sports', 'fitness']],
  [Armchair, ['moveis', 'furniture', 'decor']],
  [CookingPot, ['utilidades', 'housewares', 'cozinha', 'la_cuisine', 'casa_conforto']],
  [Watch, ['relogio', 'watches']],
  [Car, ['automotivo', 'auto']],
  [ToyBrick, ['brinquedo', 'toys', 'cool_stuff']],
  [Baby, ['bebe', 'baby', 'fraldas']],
  [PencilRuler, ['papelaria', 'stationery', 'office']],
  [Shirt, ['fashion', 'roupa', 'moda', 'calcados', 'underwear', 'clothing']],
  [Luggage, ['malas', 'luggage']],
  [PawPrint, ['pet']],
  [BookOpen, ['livro', 'book', 'dvd_blu_ray']],
  [Hammer, ['ferramenta', 'construcao', 'construction', 'tools', 'industria', 'seguranca']],
  [Flower2, ['jardim', 'garden', 'flores', 'flowers']],
  [Wine, ['bebida', 'drinks', 'alimento', 'food']],
  [Gift, ['presente', 'gift', 'party', 'festa', 'natal']],
  [Palette, ['artes', 'arts', 'art']],
]

/** Ícone lucide da categoria (a Olist não tem foto de produto). Sem correspondência: Package. */
export function categoryIcon(category: string | null | undefined): LucideIcon {
  const key = (category ?? '').toLowerCase()
  if (!key) return Package
  for (const [icon, words] of RULES) {
    if (words.some((word) => key.includes(word))) return icon
  }
  return Package
}

# Loja: especificação de UX/UI (E9)

Escopo: só a loja (`frontend/`, porta 8080). Nada aqui menciona o painel administrativo; a extração dele está na seção 5. Base: `docs/plano-loja-simulada.md` (D8, E8, E9, D4, D6, D9). Pagamento simulado, MFA por e-mail, frete por CEP. Nada implementado ainda.

## 1. Arquitetura de informação e rotas

Princípio: a loja é o produto. Hoje a home vende "dataset e análise" (hero "Produtos, preços e notas", KPIs de contagem, rodapé de licença). Passa a vender produtos; a atribuição Olist (CC BY-NC-SA) vai para o rodapé e para a página "Sobre esta demo".

| Rota | Tela | Acesso |
|---|---|---|
| `/` | Home | público |
| `/categorias` | Todas as categorias | público |
| `/c/:categoria` | Listagem de categoria (filtros, ordenação) | público |
| `/busca?q=` | Resultados da busca (mesma listagem) | público |
| `/produtos/:id` | Produto | público |
| `/carrinho` | Carrinho (página; no desktop também gaveta) | público (convidado local) / conta |
| `/checkout` | Checkout em etapas: `?etapa=endereco\|frete\|pagamento\|revisao` | conta |
| `/pedido/:id/confirmacao` | Confirmação | conta |
| `/conta` | Visão geral da conta | conta |
| `/conta/pedidos` e `/conta/pedidos/:id` | Pedidos e detalhe | conta |
| `/conta/enderecos` | Endereços (máx. 3) | conta |
| `/conta/seguranca` | Senha, MFA, dispositivos confiáveis | conta |
| `/conta/privacidade` | Exportar dados, corrigir, excluir conta | conta |
| `/entrar` | Login (e-mail + senha) | público |
| `/entrar/codigo` | Código OTP de 6 dígitos | meio do login |
| `/cadastro` | Cadastro (apelido, e-mail, senha, aceite) | público |
| `/cadastro/codigo` | OTP de verificação do e-mail | meio do cadastro |
| `/privacidade` | Política de privacidade (versionada) | público |
| `/termos` | Termos de uso | público |
| `/sobre` | Sobre a demo: pagamento simulado, dados Olist, licença, 18+ | público |
| `*` | 404 | público |

Navegação global: logo, caixa de busca (centro, domina o header), Conta, Carrinho com contador. Segunda faixa (desktop): "Todas as categorias" (megamenu) + 6 a 8 categorias mais vendidas. Rodapé: Ajuda (Sobre a demo), Privacidade, Termos, Minha conta, atribuição Olist. `?redirect=` usa `safeRedirect` existente (`lib/navigation.ts`), restrito a caminhos da loja.

Carrinho de convidado: guardado em `localStorage` (chave própria da loja), mesclado ao carrinho do servidor ao entrar. Finalizar compra exige conta (redireciona a `/entrar?redirect=/checkout`).

## 2. Wireframes

Legenda: `[ ]` botão/campo, `(img)` imagem gerada (seção 3). Mobile: coluna única, barra inferior fixa de navegação (Início, Categorias, Busca, Carrinho, Conta).

### Header global

Desktop (altura 64 + faixa de 40):
```
[■ LOJA]  [ Buscar produtos, categorias...        (lupa) ]   Entrar | Conta   [Carrinho 2]
 Todas as categorias v   Cama e banho  Beleza  Informática  Esporte  Móveis  Brinquedos ...
```
Mobile (altura 56):
```
[☰]  [■ LOJA]                         [lupa] [Carrinho 2]
```
Busca mobile abre tela cheia com campo, sugestões e buscas recentes.

### Home

Desktop:
```
+--------------------------------------------------------------+
| Aviso demo (fino): Loja de demonstração. Pagamento simulado. |
+--------------------------------------------------------------+
| BANNER (2 slides, rotação manual + setas)                    |
| [texto grande: chamada da categoria]    (composição gerada)  |
| [Ver ofertas]                                    o  .  .     |
+--------------------------------------------------------------+
| Frete por CEP | Pagamento simulado | Troca em 7 dias (demo) |
+--------------------------------------------------------------+
| Comprar por categoria                                        |
| (ico)Cama  (ico)Beleza  (ico)Info  (ico)Esporte  ... x12     |
+--------------------------------------------------------------+
| Mais vendidos                                   Ver todos -> |
| [card][card][card][card][card][card]                         |
+--------------------------------------------------------------+
| Melhor avaliados (nota >= 4,5 e >= 20 avaliações)            |
| [card] x6 (carrossel com scroll-snap)                        |
+--------------------------------------------------------------+
| Vitrine: Cama, mesa e banho    (faixa de 6 produtos)         |
| Vitrine: Beleza e saúde        (faixa de 6 produtos)         |
+--------------------------------------------------------------+
| Rodapé                                                       |
+--------------------------------------------------------------+
```
Mobile: banner 4:5 com 1 slide visível; categorias em fileira rolável horizontal (chips com ícone); vitrines em carrossel com scroll-snap, 2 cards visíveis e meio.

### Listagem (categoria e busca)

Desktop:
```
Início > Cama, mesa e banho                      1.240 produtos
+----------------+  Ordenar: [Mais vendidos v]   Chips ativos: [Nota 4+ x] [até R$100 x]  Limpar
| FILTROS        |  +------+ +------+ +------+ +------+
| Categoria      |  |(img) | |(img) | |(img) | |(img) |
|  (lista)       |  | card | | card | | card | | card |
| Preço          |  +------+ +------+ +------+ +------+
|  [min]-[max]   |  ... 24 por página ...
| Nota           |  [< 1 2 3 ... 52 >]
|  4+ 3+ 2+      |
| Disponibilidade|
|  [x] em estoque|
+----------------+
```
Mobile: barra fixa abaixo do header com `[Filtros (2)]` e `[Ordenar]`; ambos abrem `Sheet`/`Drawer` (já existem em `components/ui`) em tela cheia, com "Aplicar (N resultados)" fixo no rodapé. Grid de 2 colunas.

Busca: mesma tela, título `Resultados para "termo"`. Sem resultado: estado vazio com sugestão de categorias. Sugestões na caixa de busca (desktop dropdown, mobile tela cheia): 5 produtos + 3 categorias, ao digitar 2+ caracteres (debounce existente `useDebouncedValue`).

### Produto

Desktop:
```
Início > Cama, mesa e banho > Produto #ab12
+---------------------------+  Cama mesa banho (link)
| (img principal 1:1)       |  Título do produto
| [t1][t2][t3][t4] miniaturas|  ★★★★☆ 4,3 (128 avaliações)
+---------------------------+  R$ 89,90
                               ou 3x de R$ 29,96 sem juros (simulado)
                               Em estoque: 14 un.   [Quantidade - 1 +]
                               [  Adicionar ao carrinho  ]  [Comprar agora]
                               Calcular frete: [CEP____-___] [OK]
                               -> Entrega em 4 a 6 dias úteis: R$ 18,40
+--------------------------------------------------------------+
| Abas: Descrição | Especificações | Avaliações                |
| Especificações: peso, comprimento, altura, largura (tabela)  |
| Avaliações: nota média, distribuição 5..1 (barras), total    |
+--------------------------------------------------------------+
| Quem viu também comprou: [card] x6                           |
+--------------------------------------------------------------+
```
Mobile: galeria em carrossel com scroll-snap e indicador de pontos; título, preço e nota; barra fixa inferior com `[Adicionar ao carrinho]` (com o preço); frete e abas em acordeão (`accordion` existente).

Dados reais usados: peso, dimensões, `avg_rating`, `review_count`, `photos_qty` (quantidade de miniaturas, máx. 5), `units_sold` ("128 vendidos"). Descrição: o dataset não tem texto; a aba "Descrição" mostra texto template curto por categoria, claramente genérico, ou é omitida. Recomendação: omitir e mostrar só "Especificações". Avaliações: só nota 1 a 5 e distribuição (sem texto de cliente, sem nome).

### Carrinho

Desktop (página e gaveta; a gaveta é a mesma lista em `Sheet` lateral, abre ao adicionar):
```
Carrinho (3 itens)
+--------------------------------------------+  +----------------+
| (img) Título          [- 2 +]  R$ 179,80  x |  | Resumo         |
|       Em estoque                            |  | Subtotal  R$   |
| (img) Título          [- 1 +]  R$  49,90  x |  | Frete  [CEP]   |
|       Restam 2 unidades                     |  | Total    R$    |
+--------------------------------------------+  | [Finalizar]    |
 Guardar para depois | Continuar comprando        | Pagamento      |
                                                 | simulado       |
                                                 +----------------+
```
Mobile: itens empilhados, resumo e `[Finalizar compra  R$ 229,70]` fixos na base. Total mostrado é estimativa; o servidor recalcula tudo (D4).

### Checkout em etapas

Indicador: `1 Endereço  >  2 Frete  >  3 Pagamento  >  4 Revisão`, cada etapa concluída editável. Header reduzido (só logo, "Compra segura (simulada)", sem busca, sem categorias). Desktop: etapa à esquerda, resumo do pedido fixo à direita. Mobile: etapa em tela cheia, resumo recolhível no topo ("Resumo R$ 229,70 v").
```
1 ENDEREÇO               2 FRETE                  3 PAGAMENTO (SIMULADO)
( ) Casa - Rua..., SP    (•) Padrão  4-6 dias     [ Número do cartão   ]
( ) + novo (CEP,cidade,UF)    R$ 18,40            [ Validade ] [ CVV   ]
[Continuar]              ( ) Econômico 7-10 dias  Cartões de teste:
                              R$ 11,20            ...0001 aprova, ...0002 recusa,
                         [Continuar]              ...0003 simula timeout
                                                  [Continuar]
4 REVISÃO
Itens, endereço, frete, cartão (••••1111), total. [Confirmar pedido R$ 229,70]
Texto: "Nenhum valor será cobrado. Pagamento simulado."
```
Regras: o campo de cartão aceita só os cartões de teste e o aviso fica visível acima do campo; o PAN nunca é exibido depois (só bandeira e últimos 4). Botão Confirmar desabilita durante o envio e usa `Idempotency-Key` (D4). Recusado: volta à etapa 3 com mensagem e dados preservados. Timeout: mensagem "Não conseguimos confirmar", botão "Tentar novamente" reusa a mesma chave.

### Confirmação

```
✓ Pedido recebido            Pedido #A1B2C3 · 13/11/2026
Previsão de entrega: 4 a 6 dias úteis
Itens | Endereço | Frete | Pagamento (cartão ••••1111, simulado) | Total
[Acompanhar pedido]  [Continuar comprando]
```
Mobile: mesmo conteúdo, botões em largura total. Foco vai ao título ao abrir; recarregar a página mantém a confirmação (dado do servidor, não do estado local).

### Conta e pedidos

Desktop: menu lateral (Visão geral, Pedidos, Endereços, Segurança, Privacidade) + conteúdo. Mobile: lista de seções na tela `/conta`, cada uma abre sua página com botão voltar.
```
Pedidos
+--------------------------------------------------------+
| #A1B2C3   13/11/2026   Enviado   R$ 229,70   [Detalhes]|
| #A1B2C0   02/11/2026   Entregue  R$  89,90   [Detalhes]|
+--------------------------------------------------------+
Detalhe: linha do tempo (Criado > Pago > Enviado > Entregue), itens, endereço, total, ação "Cancelar" só se criado/pago.
Privacidade: [Exportar meus dados (JSON)]  [Corrigir dados]  [Excluir minha conta] (pede reautenticação + confirmação digitada)
Segurança: trocar senha; "confiar neste dispositivo por 30 dias" ligado/desligado.
```

### Login, cadastro e OTP

Tela única centralizada (largura 400), sem header de busca.
```
/entrar            /entrar/codigo               /cadastro
E-mail [   ]       Enviamos um código para      Apelido (opcional) [  ]
Senha  [   ] (olho) a***@gmail.com              E-mail [  ]
[Entrar]           [ _ _ _ _ _ _ ]  (6 caixas)  Senha [  ] (mín. 12, medidor)
Criar conta        [Verificar]                  [x] Li e aceito Termos e Política
Esqueci a senha    Reenviar em 0:42 | Voltar    [x] Tenho 18 anos ou mais
                   [x] Confiar neste disp.      [Criar conta]
```
O OTP aceita colar o código inteiro, `autocomplete="one-time-code"`, `inputmode="numeric"`. Mensagens de erro genéricas ("E-mail ou senha incorretos"; "Código inválido ou expirado") para não enumerar contas. Cadastro responde igual para e-mail novo e existente: "Se o e-mail puder ser usado, enviamos um código." Contagem regressiva de 60 s para reenvio. Após 5 erros: "Código bloqueado. Peça um novo."

### Política e termos

Coluna de leitura de 68ch, índice fixo à esquerda no desktop (âncoras), no mobile índice em acordeão no topo. Versão e data no topo (`Versão 1 · 13/11/2026`). Aceite no cadastro grava a versão.

## 3. Direção visual

Conceito: loja de papelaria-gráfica brasileira, não "marketplace colorido". Mantém o sistema atual: monocromático, alto contraste, cantos retos (`--radius` 0 a 2px), Archivo, títulos `display` (800, caixa alta, tracking -0.045em), `eyebrow` em 11px caixa alta. O que muda: ritmo e densidade de e-commerce (cards compactos, preço protagonista, selos, faixas de vitrine) e uma única cor de ação.

Tokens (em `index.css`, mesmos nomes):
- Mantém `--background`, `--foreground`, `--surface`, `--border`, `--muted-foreground`, `--destructive`.
- Novo `--brand: oklch(0.58 0.2 32)` (vermelho-laranja queimado) e `--brand-foreground: oklch(1 0 0)`. Uso exclusivo: botão primário de compra (Adicionar, Comprar agora, Confirmar pedido), selo de desconto/estoque baixo, contador do carrinho, foco de busca. Todo o resto continua preto e branco. Contraste do texto branco sobre `--brand` >= 4,5:1 (conferir; se falhar, reduzir luminosidade para 0.52).
- Novo `--success: oklch(0.5 0.12 150)` só para "Em estoque", "Entregue" e confirmação.
- Dark mode: fora de escopo.

Tipografia: Archivo (já usada). Escala: título de página 28/36 mobile e 40/48 desktop (não os 72-96 px do hero atual, exceto o banner da home); nome do produto 14/20 semibold em card, 28/34 extrabold na página; preço 18 extrabold em card, 32 na página, `tabular-nums`; preço antigo/parcelado em 12 muted. Fonte self-host (`@fontsource-variable/archivo` ou arquivo em `public/fonts`), removendo `fonts.googleapis.com` do `index.html` (plano D8/E9). Prefixos de número em `tabular-nums` em todo valor monetário.

Espaçamento: grade de 4 px; container `max-w-[1600px]` com `px-4 md:px-8` (igual ao atual); seções com `py-10 md:py-14` (a home atual usa `py-14 md:py-24`, espaçoso demais para loja); cards com gap 12 mobile e 16 desktop; bordas de 1px como separador (grade "gap-px bg-border" já usada em categorias, manter como assinatura).

Evitar visual genérico de IA: sem gradiente roxo/azul, sem glassmorphism, sem cartões arredondados com sombra suave, sem emoji nem ilustração de pessoa genérica, sem "hero com três ícones e três bullets" (a faixa de benefícios fica fina, em uma linha, texto real). Banner com tipografia grande e composição gráfica gerada, não foto de banco.

### Como suprir a ausência de fotos

O dataset não tem imagem; só `category`, `photos_qty`, peso e dimensões. Hoje `ProductThumb` mostra o ícone lucide da categoria em cinza (`bg-surface`, ícone 1/3 do lado). Evoluir `ProductThumb` (mesmo componente, mesma API com `productId` opcional) para uma capa gerada determinística, sem rede, sem custo:
1. Cor: de um conjunto de 6 tons neutros quentes/frios de baixa saturação (por exemplo oklch L 0.93, C 0.015 a 0.03, hue 30, 90, 150, 210, 270, 330) escolhido por hash de `product_id`. Mesmo produto sempre tem a mesma capa; produtos da mesma categoria variam entre si, o que quebra a monotonia da grade.
2. Composição: ícone da categoria (já existe `categoryIcon`) em traço 1.25, mas com 4 variações escolhidas pelo hash: centralizado; grande e cortado no canto; repetido em grade de padrão com opacidade 8%; acompanhado de linhas de cota.
3. Cota real: na capa 1:1 de card, canto inferior mostra as dimensões reais em mono pequeno ("32 × 24 × 8 cm · 1,2 kg") quando existirem. Dá informação verdadeira onde a foto estaria.
4. Galeria da página de produto: `photos_qty` define o número de miniaturas (1 a 5; nulo vira 1). As miniaturas são as variações de composição acima, mais uma última com o desenho técnico das dimensões (caixa com altura, largura, comprimento). Nenhuma delas finge ser foto.
5. Honestidade: legenda discreta única na página de produto ("Imagem ilustrativa: o catálogo não tem fotos") e a nota de demo no rodapé; remover a frase técnica atual ("O dataset Olist não tem foto...") do corpo principal da página.
6. Rótulo do produto: `label` sintético ("categoria_en · #abc12345") é feio como título de loja. Derivar um título legível no cliente: `Categoria · Modelo AB12` (usa `categoryLabel` e os 4 primeiros caracteres maiúsculos do id). Se o backend passar a fornecer `title`, trocar sem mudar UI.
7. Acessibilidade: capa decorativa mantém `aria-hidden`; o link do card tem o título como texto. Nada de informação só na imagem (cotas também aparecem em Especificações).

Banners e vitrines: composições tipográficas feitas em CSS (bloco de cor + nome da categoria em `display` + ícone grande em traço), não imagens.

## 4. Componentes, estados e acessibilidade

Reaproveitados (sem mudança): `ui/button`, `input`, `label`, `select`, `badge`, `card`, `skeleton`, `sheet`, `drawer`, `dialog`, `alert-dialog`, `accordion`, `tabs`, `slider` (faixa de preço), `sonner` (toasts), `Pagination`, `RatingStars`, `Specs`, `ProductCard`, `ProductCardSkeleton`, `EmptyState`, `ErrorState`, `PageHeader` (só para páginas de conta/política, tamanho reduzido), `useDebouncedValue`, `usePageTitle`, `useProducts`/`useCategories`, `lib/format`, `lib/searchParams`, `lib/navigation`.

Alterados: `PublicLayout` vira `ShopLayout` (header com busca, megamenu, carrinho; rodapé de loja; remove link do painel), `Brand` (nome da loja), `ProductThumb` (capa gerada), `ProductCard` (preço maior, selo de estoque, botão rápido "Adicionar" no hover/foco no desktop), `HomePage`, `ProdutosPage`, `ProdutoPage` (galeria, compra, frete, abas), `StateViews` (adicionar `OutOfStock`, `InlineError`), `index.css` (tokens `--brand`, `--success`).

Novos: `SearchBox` (com sugestões, combobox ARIA), `MegaMenu`, `MobileTabBar`, `Banner`/`PromoStrip`, `ProductShelf` (faixa com scroll-snap), `FilterPanel` (+ versão em `Sheet`), `ActiveFilterChips`, `Gallery`, `QuantityStepper`, `ShippingCalculator` (CEP), `StockBadge`, `PriceBlock`, `CartDrawer`, `CartLine`, `OrderSummary`, `CheckoutSteps`, `AddressForm`/`AddressCard`, `ShippingOption`, `FakeCardForm` (com aviso e cartões de teste), `OrderStatusTimeline`, `OtpInput`, `PasswordField` (olho, medidor), `AccountNav`, `LegalDocument`, `DemoNotice`, `RequireCustomer` (rota protegida), `CustomerAuthProvider` (chave `localStorage` própria da loja).

Estados por tela (todos obrigatórios):
- Carregando: skeleton com a forma final (já existe para card e detalhe); botões de envio com spinner e `aria-busy`; nunca tela em branco. Transições de rota mantêm a página atual (o `lazy` do router já faz isso).
- Vazio: carrinho ("Seu carrinho está vazio" + categorias populares), busca sem resultado (termo, dicas, categorias), listagem filtrada sem resultado (`Limpar filtros`), pedidos ("Você ainda não comprou nada"), endereços.
- Erro: `ErrorState` com "Tentar de novo" para falha de lista; erro de campo inline abaixo do campo, ligado por `aria-describedby`; erro de rede no checkout preserva o formulário; 404 de produto e de pedido com `EmptyState`; 401 expulsa para `/entrar?redirect=`.
- Sem estoque: card com selo "Esgotado", imagem em 60% de opacidade e sem botão rápido; página do produto com `Adicionar` desabilitado e texto "Avise-me" omitido (fora de escopo); estoque baixo (<= 5) mostra "Restam N" com `--brand`; no carrinho, item que perdeu estoque mostra aviso, ajusta a quantidade ao máximo disponível e bloqueia a finalização até o usuário confirmar; no checkout, estoque insuficiente na confirmação volta ao carrinho com mensagem por item.
- Pagamento: recusado, timeout e sucesso têm texto e foco definidos (seção 2).
- Offline/lento: toast discreto, ação repetível.

Acessibilidade (WCAG 2.2 AA como alvo):
- Contraste >= 4,5:1 texto, 3:1 componentes e foco. Foco visível sempre (`ring` atual de 1px em preto é fino: usar 2px com offset 2px no botão `--brand`).
- Link "Pular para o conteúdo" no início do layout; um `h1` por página; landmarks `header`, `nav` com `aria-label`, `main`, `footer`.
- Busca: padrão combobox (`role="combobox"`, `aria-expanded`, `aria-activedescendant`), setas e Esc.
- Gaveta, sheets e dialogs usam Radix (foco preso, Esc, retorno de foco). Gaveta do carrinho anuncia item adicionado via região `aria-live="polite"`.
- Carrinho: botões de quantidade com rótulo ("Diminuir quantidade de <produto>"), remover com desfazer em toast.
- Formulários: `label` visível, `autocomplete` correto (`email`, `new-password`, `current-password`, `postal-code`, `street-address`, `one-time-code`), máscara de CEP sem bloquear colagem, erros em `role="alert"` apenas no envio.
- Estrelas já têm `role="img"` com texto; manter. Filtros: grupos com `fieldset`/`legend`; contagem de resultados em `aria-live`.
- Alvos de toque >= 44 px no mobile; `prefers-reduced-motion` respeitado (sem rotação automática do banner, `motion-reduce:animate-none` nos skeletons como hoje).
- Carrossel: setas com botão, scroll-snap nativo, sem auto-play.
- Privacidade (D9): sem analytics, sem fontes externas, sem imagens de terceiros. Aviso 18+ no cadastro; aviso de demo em todas as páginas (faixa fina fechável por sessão) e no checkout (permanente).

## 5. Extração do painel para `frontend-admin/`

Mover (cópia para o novo projeto, remoção da loja):
- `src/pages/Backoffice/*` (CategoriasPage, LoginPage, ProdutoAdminPage, ProdutosAdminPage, VisaoGeralPage)
- `src/pages/Assistente/AssistentePage.tsx`, `assistente.css`
- `src/components/backoffice/*` (KpiCard, MonthlyChart, PageTitle, RatingBars, Sidebar)
- `src/components/chat/*` (Composer, MessageList)
- `src/components/layout/BackofficeLayout.tsx`
- `src/components/RequireAdmin.tsx`
- `src/app/AuthProvider.tsx`, `auth-context.ts` (versão admin; a loja ganha `CustomerAuthProvider` próprio)
- `src/hooks/useAuth.ts`, `useBackoffice.ts`, `useChat.ts`
- `src/services/backoffice.ts`, `chat.ts`, `chat.test.ts`, `auth.ts` (login de admin)
- `src/types/chat.ts`, `src/types/auth.ts` (versão admin)
- Em `src/types/product.ts`: `MonthlyPoint`, `AdminProductRow`, `RatingBucket`, `TopSeller`, `AdminProductDetail`, `AdminCategoryRow`, `Kpis`, `Overview`, `AdminProductFilters`, `AdminProductSort`, `SortOrder`
- Em `src/lib/product.ts`: `backofficeProductHref`
- Em `src/lib/navigation.ts`: a regra de `/backoffice/login` em `safeRedirect`
- Em `src/app/router.tsx`: todas as rotas `backoffice/*` e o redirect `assistente`
- Dependência `recharts` sai do `package.json` da loja (só gráficos do painel).
- `src/lib/sse.ts` e `sse.test.ts`: só o chat usa; mover junto (confirmar com grep antes).

Ficam na loja: `pages/Vitrine/*` (reescritas), `components/product/*`, `components/ui/*`, `components/layout/{PublicLayout→ShopLayout, Brand}`, `StateViews`, `PageHeader`, `app/{router, RouteError}`, `hooks/{useProducts, useDebouncedValue, usePageTitle}`, `lib/{categoryIcons, format, pagination, product, searchParams, utils, navigation}`, `services/{http, products}`, `types/product.ts` (só tipos públicos), `index.css`, `main.tsx`, `public/`.

Compartilhados com o novo projeto por alias de caminho, sem copiar (D8): `components/ui/*`, `lib/{utils, format}`, tokens de `index.css`. O admin importa; a loja nunca importa de `frontend-admin/`. Se o alias exigir, extrair os tokens para um `shared/tokens.css`.

Edições na loja além de remover arquivos: tirar o link "Backoffice" de `PublicLayout.tsx` (linha 21) e o botão "Entrar no backoffice" de `HomePage.tsx`; trocar o comentário do `router.tsx`; `services/http.ts` troca a chave `olist.token` por chave da loja (`shop.token`) e passa a tratar 401 de cliente; ajustar `<title>` e descrição do `index.html` para loja; `README.md` e `nginx.conf` (porta 8080 só com loja; admin vai ao outro `server` de 8081).

Verificação: `grep -ri "backoffice\|assistente\|admin" frontend/src frontend/index.html frontend/nginx.conf` vazio; bundle da loja sem `recharts` nem código de chat (conferir `dist/assets`); `npm run build` nos dois projetos.

## 6. Critérios de pronto por tela (testáveis)

Geral, valem para toda tela: sem erro de console; `axe` sem violação crítica ou séria; navegação completa só por teclado; sem scroll horizontal em 360, 768 e 1280 px; LCP < 2,5 s em build local com 4x CPU throttle; nenhuma requisição a domínio externo (aba Network); nenhuma ocorrência de "backoffice" no DOM.

| Tela | Pronto quando |
|---|---|
| Header e rodapé | Busca, conta e carrinho acessíveis em 360 px; contador do carrinho atualiza ao adicionar; "Pular para o conteúdo" é o primeiro foco; rodapé tem Privacidade, Termos, Sobre, atribuição Olist. |
| Home | Mostra banner, 12 categorias, "Mais vendidos" e "Melhor avaliados" com dados da API; cada card leva ao produto; skeleton antes dos dados; falha da API mostra `ErrorState` por seção e a seção seguinte ainda carrega; nenhum KPI de dataset. |
| Categoria e busca | Filtro de preço, nota e ordenação alteram a URL e o resultado; recarregar mantém o estado; chip remove filtro; 0 resultado mostra estado vazio com "Limpar filtros"; paginação com 24 itens; no mobile filtros abrem em `Sheet` e "Aplicar" mostra a contagem. |
| Busca (sugestões) | Digitar 2+ caracteres mostra sugestões em <= 400 ms após a pausa; setas e Enter funcionam; Esc fecha; leitor de tela anuncia a quantidade. |
| Produto | Galeria com `photos_qty` miniaturas (1 a 5), troca por clique e teclado; preço, nota, estoque e especificações reais; CEP válido mostra frete e prazo; CEP inválido mostra erro no campo; esgotado desabilita compra; 404 mostra `EmptyState`; barra de compra fixa no mobile. |
| Carrinho | Adicionar, alterar, remover (com desfazer) atualizam total; quantidade limitada ao estoque; item sem estoque sinalizado; convidado mantém itens após recarregar e ao entrar; carrinho vazio mostra categorias; total final bate com o do servidor. |
| Checkout | Etapas em ordem, só avança com etapa válida; voltar preserva dados; cartão 0001 aprova, 0002 recusa e volta à etapa 3, 0003 permite repetir com a mesma `Idempotency-Key` sem duplicar pedido; clicar duas vezes em Confirmar cria 1 pedido; PAN nunca aparece depois (só bandeira e 4 últimos); aviso "pagamento simulado" visível na etapa 3 e na revisão. |
| Confirmação | Mostra número, itens, total e previsão; recarregar mantém; pedido de outro cliente retorna 404; foco inicial no título. |
| Conta e pedidos | Lista só pedidos do cliente logado; detalhe mostra linha do tempo e estado vindo do servidor; cancelar só em estados permitidos; endereços limitados a 3 (quarto bloqueado com mensagem); exportar baixa JSON só com dados próprios; excluir exige reautenticação e texto de confirmação, e depois desloga. |
| Login, cadastro, OTP | Mensagem de erro igual para e-mail inexistente e senha errada; cadastro responde igual para e-mail novo e existente; OTP aceita colar 6 dígitos, bloqueia após 5 erros, reenvio só após 60 s; senha < 12 caracteres rejeitada; cadastro sem aceite de termos e 18+ não envia; `?redirect=` externo é ignorado; sessão da loja não funciona em outro app. |
| Política, termos, sobre | Renderizam texto versionado com data; índice por âncora funciona; aceite do cadastro cita a versão exibida. |
| 404 | Mostra `EmptyState` com link para o início, dentro do layout da loja. |
| Extração (E8) | `grep -ri backoffice frontend/src` vazio; `npm run build` verde nos dois projetos; bundle da loja sem `recharts`; token de um app não vale no outro; assistente funciona na porta 8081. |

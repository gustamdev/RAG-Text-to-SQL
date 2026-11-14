# frontend-admin

Backoffice (painel admin + assistente de dados) do Olist Insights, servido separado da loja.

## Dependências

O `package.json` daqui é espelhado à mão de `frontend/package.json`; não há lockfile próprio. O Docker usa o lock da loja, então há um só React e as mesmas versões nos dois apps. Mudou versão na loja: replique aqui. `recharts` continua em `frontend/package.json`.

`components/ui` e `lib` vêm de `../frontend/src` via alias no `vite.config.ts`.

## Duplicações aceitas

Peças pequenas (StateViews, Brand, Pagination...) estão duplicadas em `src/` de propósito, para não acoplar os dois apps.

## Rodar

Com `frontend/node_modules` instalado, linke-o: `ln -s ../frontend/node_modules node_modules`.

- dev: `npm run dev` (porta 5174, proxy `/api` para `localhost:8000`)
- test: `npm test`
- build: `npm run build`

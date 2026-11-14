import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from 'recharts'
import { brl, monthLabel, num } from '@/lib/format'
import type { MonthlyPoint } from '@/types/product'

const REVENUE_COLOR = 'var(--foreground)'
const UNITS_COLOR = 'oklch(0.62 0 0)'
const AXIS_TICK = { fontSize: 11, fill: 'var(--muted-foreground)' }

function MonthlyTooltip({ active, payload, label }: TooltipContentProps) {
  const point = payload?.[0]?.payload as MonthlyPoint | undefined
  if (!active || !point) return null
  return (
    <div className="border border-border bg-popover px-3 py-2 text-xs shadow-sm">
      <p className="eyebrow mb-1.5">{monthLabel(String(label ?? point.month))}</p>
      <dl className="space-y-0.5 tabular-nums">
        <div className="flex justify-between gap-6">
          <dt className="text-muted-foreground">Receita</dt>
          <dd className="font-semibold">{brl(point.revenue)}</dd>
        </div>
        <div className="flex justify-between gap-6">
          <dt className="text-muted-foreground">Unidades</dt>
          <dd className="font-semibold">{num(point.units)}</dd>
        </div>
        <div className="flex justify-between gap-6">
          <dt className="text-muted-foreground">Pedidos</dt>
          <dd className="font-semibold">{num(point.orders)}</dd>
        </div>
      </dl>
    </div>
  )
}

/** Receita (barras, eixo esquerdo) e unidades (linha, eixo direito) por mês. Aceita qualquer nº de meses. */
export function MonthlyChart({ data, height = 300 }: { data: MonthlyPoint[]; height?: number }) {
  if (data.length === 0) {
    return <p className="py-16 text-center text-sm text-muted-foreground">Sem vendas no período.</p>
  }

  return (
    <figure>
      <div className="mb-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-2">
          <span aria-hidden="true" className="size-2.5" style={{ background: REVENUE_COLOR }} />
          Receita (R$)
        </span>
        <span className="inline-flex items-center gap-2">
          <span aria-hidden="true" className="h-0.5 w-4" style={{ background: UNITS_COLOR }} />
          Unidades
        </span>
      </div>
      <div style={{ height }} role="img" aria-label="Gráfico mensal de receita e unidades vendidas">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey="month"
              tickFormatter={monthLabel}
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={{ stroke: 'var(--border)' }}
              minTickGap={12}
            />
            <YAxis
              yAxisId="revenue"
              tickFormatter={(v: number) => brl(v, { compact: true })}
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={false}
              width={64}
            />
            <YAxis
              yAxisId="units"
              orientation="right"
              tickFormatter={(v: number) => num(v, { compact: true })}
              tick={AXIS_TICK}
              tickLine={false}
              axisLine={false}
              width={48}
            />
            <Tooltip content={MonthlyTooltip} cursor={{ fill: 'var(--accent)', opacity: 0.6 }} />
            <Bar yAxisId="revenue" dataKey="revenue" fill={REVENUE_COLOR} maxBarSize={44} isAnimationActive={false} />
            <Line
              yAxisId="units"
              dataKey="units"
              type="monotone"
              stroke={UNITS_COLOR}
              strokeWidth={2}
              dot={{ r: 3, fill: 'var(--background)', stroke: UNITS_COLOR, strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <table className="sr-only">
        <caption>Receita, unidades e pedidos por mês</caption>
        <thead>
          <tr>
            <th>Mês</th>
            <th>Receita</th>
            <th>Unidades</th>
            <th>Pedidos</th>
          </tr>
        </thead>
        <tbody>
          {data.map((p) => (
            <tr key={p.month}>
              <td>{monthLabel(p.month)}</td>
              <td>{brl(p.revenue)}</td>
              <td>{num(p.units)}</td>
              <td>{num(p.orders)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}

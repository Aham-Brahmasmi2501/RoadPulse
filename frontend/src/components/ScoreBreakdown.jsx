// Per-component priority score breakdown. Each row shows the points earned
// out of the component's maximum weight, so reviewers can see *why* a site ranks high.
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { SEV_COLOR } from '../lib/format'

const COMPONENT_COLOR = {
  size: '#f97316',
  confidence: '#38bdf8',
  sightings: '#a78bfa',
  defect_type: '#f472b6',
  road_context: '#facc15',
  recency: '#34d399',
}

function BreakdownTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg border border-navy-600 bg-navy-900 px-3 py-2 text-xs shadow-xl">
      <div className="font-semibold text-white">{d.label}</div>
      <div className="text-slate-300">
        {d.points} / {d.weight} pts · {d.detail}
      </div>
      <div className="text-slate-500">normalised {d.normalized}</div>
    </div>
  )
}

export default function ScoreBreakdown({ components, score, severity, height = 170, compact = false }) {
  if (!components?.length) return <div className="text-xs text-slate-500">No score yet</div>
  const data = components.map((c) => ({ ...c, rest: Math.max(0, +(c.weight - c.points).toFixed(1)) }))
  const max = Math.max(...components.map((c) => c.weight))
  return (
    <div>
      {score !== undefined && (
        <div className="mb-1 flex items-baseline justify-between">
          <span className="text-[11px] uppercase tracking-wide text-slate-400">Priority score breakdown</span>
          <span className="text-sm font-bold" style={{ color: SEV_COLOR[severity] || '#e2e8f0' }}>
            {Math.round(score)}
            <span className="text-xs font-normal text-slate-500">/100</span>
          </span>
        </div>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ top: 2, right: 46, bottom: 2, left: 0 }} barCategoryGap={compact ? 3 : 5}>
          <XAxis type="number" domain={[0, max]} hide />
          <YAxis
            type="category"
            dataKey="label"
            width={compact ? 84 : 96}
            tick={{ fill: '#94a3b8', fontSize: compact ? 10 : 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<BreakdownTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
          <Bar dataKey="points" stackId="a" radius={[3, 0, 0, 3]} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.key} fill={COMPONENT_COLOR[d.key] || '#f97316'} />
            ))}
          </Bar>
          <Bar dataKey="rest" stackId="a" fill="#1c2b4a" radius={[0, 3, 3, 0]} isAnimationActive={false}
            label={(p) => <PointsLabel {...p} data={data} />} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// Writes "12.5/25" to the right of each bar
function PointsLabel({ x, y, width, height, index, data }) {
  const d = data[index]
  if (!d) return null
  return (
    <text x={x + width + 4} y={y + height / 2} dy={3.5} fill="#94a3b8" fontSize={10}>
      {d.points}/{d.weight}
    </text>
  )
}

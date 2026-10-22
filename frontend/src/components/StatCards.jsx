import { useEffect, useState } from 'react'
import { AlertOctagon, CheckCircle2, FileStack, MapPin } from 'lucide-react'
import { api } from '../lib/api'

function Card({ icon: Icon, label, value, hint, accent }) {
  return (
    <div className="card flex items-center gap-4 px-4 py-3.5">
      <div className="rounded-xl p-2.5" style={{ background: `${accent}1f`, color: accent }}>
        <Icon size={20} />
      </div>
      <div className="min-w-0">
        <div className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</div>
        <div className="text-2xl font-bold leading-tight text-white">{value}</div>
        {hint && <div className="truncate text-xs text-slate-500">{hint}</div>}
      </div>
    </div>
  )
}

export default function StatCards({ refreshKey }) {
  const [s, setS] = useState(null)
  useEffect(() => {
    api.stats().then(setS).catch(() => setS(null))
  }, [refreshKey])
  const v = (x) => (s ? x : '—')
  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      <Card icon={FileStack} label="Total reports" value={v(s?.total_reports)} accent="#38bdf8"
        hint={s ? `${s.pending_review} awaiting review` : ' '} />
      <Card icon={MapPin} label="Unique defect sites" value={v(s?.unique_sites)} accent="#a78bfa"
        hint={s ? `de-duplicated from ${s.total_reports} reports` : ' '} />
      <Card icon={AlertOctagon} label="High-priority sites" value={v(s?.high_priority_sites)} accent="#ef4444"
        hint={s ? `${s.by_severity?.medium ?? 0} medium · ${s.by_severity?.low ?? 0} low` : ' '} />
      <Card icon={CheckCircle2} label="Confirmed %" value={s ? `${s.confirmed_pct}%` : '—'} accent="#22c55e"
        hint={s ? `of ${s.reviewed} reviewed reports` : ' '} />
    </div>
  )
}

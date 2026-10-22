// Small presentational building blocks shared by every page.
import { AlertTriangle, Inbox, Loader2 } from 'lucide-react'
import { CLASS_COLOR, CLASS_LABEL, SEV_COLOR, SEV_LABEL, STATUS_STYLE } from '../lib/format'

export function ClassChip({ cls }) {
  const c = CLASS_COLOR[cls] || '#94a3b8'
  return (
    <span className="chip" style={{ background: `${c}22`, color: c, boxShadow: `inset 0 0 0 1px ${c}55` }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: c }} />
      {CLASS_LABEL[cls] || cls}
    </span>
  )
}

export function SeverityBadge({ severity, score }) {
  if (!severity) return <span className="chip bg-slate-600/20 text-slate-400">Unscored</span>
  const c = SEV_COLOR[severity]
  return (
    <span className="chip font-semibold" style={{ background: `${c}22`, color: c, boxShadow: `inset 0 0 0 1px ${c}66` }}>
      {SEV_LABEL[severity] || severity}
      {score !== undefined && score !== null && <span className="opacity-80">· {Math.round(score)}</span>}
    </span>
  )
}

export function StatusBadge({ status }) {
  return <span className={`chip capitalize ${STATUS_STYLE[status] || STATUS_STYLE.pending}`}>{status}</span>
}

export function LowConfBadge({ compact = false }) {
  return (
    <span
      className="chip bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/40"
      title="Low confidence (< 0.5). Lighting, rain, camera angle and road markings can affect predictions - please verify."
    >
      <AlertTriangle size={12} /> {compact ? 'Low conf.' : 'Low confidence'}
    </span>
  )
}

export function Spinner({ label, className = '' }) {
  return (
    <div className={`flex items-center gap-2 text-sm text-slate-400 ${className}`}>
      <Loader2 className="animate-spin text-accent" size={18} /> {label}
    </div>
  )
}

export function EmptyState({ icon: Icon = Inbox, title, children }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="mb-4 rounded-2xl bg-navy-800 p-4 ring-1 ring-navy-600">
        <Icon className="text-accent" size={28} />
      </div>
      <h3 className="text-base font-semibold text-slate-100">{title}</h3>
      <div className="mt-1 max-w-md text-sm text-slate-400">{children}</div>
    </div>
  )
}

export function ErrorBox({ error }) {
  if (!error) return null
  return (
    <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
      <b>Something went wrong:</b> {String(error.message || error)}
    </div>
  )
}

export function Segmented({ value, onChange, options }) {
  return (
    <div className="inline-flex rounded-lg bg-navy-850 p-1 ring-1 ring-navy-600">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
            value === o.value ? 'bg-accent text-white shadow' : 'text-slate-300 hover:text-white'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Toggle({ checked, onChange, label }) {
  return (
    <label className="flex cursor-pointer select-none items-center gap-2 text-sm text-slate-300">
      <span
        onClick={() => onChange(!checked)}
        className={`relative h-5 w-9 rounded-full transition ${checked ? 'bg-accent' : 'bg-navy-600'}`}
      >
        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition ${checked ? 'left-[18px]' : 'left-0.5'}`} />
      </span>
      {label}
    </label>
  )
}

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-white">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-slate-400">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  )
}

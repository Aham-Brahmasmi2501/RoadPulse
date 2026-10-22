import { Fragment, useEffect, useState } from 'react'
import { BarChart2, ChevronRight, Download, ListOrdered, MapPin } from 'lucide-react'
import { api, media } from '../lib/api'
import { CLASSES, CLASS_LABEL, ROAD_LABEL, SEV_COLOR, fmtDate, nearestPlace } from '../lib/format'
import ScoreBreakdown from '../components/ScoreBreakdown'
import { ClassChip, EmptyState, ErrorBox, PageHeader, SeverityBadge, Spinner, StatusBadge, Toggle } from '../components/ui'

function ScoreBar({ score, severity }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 overflow-hidden rounded-full bg-navy-700">
        <div className="h-full rounded-full" style={{ width: `${score}%`, background: SEV_COLOR[severity] }} />
      </div>
      <span className="w-8 text-right font-mono text-sm font-semibold text-white">{Math.round(score)}</span>
    </div>
  )
}

export default function RankingPage({ refreshKey, onZoom }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  const [includeRepaired, setIncludeRepaired] = useState(false)
  const [cls, setCls] = useState('')
  const [sev, setSev] = useState('')
  const [expanded, setExpanded] = useState(null)

  useEffect(() => {
    setRows(null)
    api.ranking({ include_repaired: includeRepaired || undefined, defect_class: cls, severity: sev })
      .then(setRows).catch((e) => { setError(e); setRows([]) })
  }, [includeRepaired, cls, sev, refreshKey])

  return (
    <div>
      <PageHeader title="Inspection list" subtitle="Defect sites ranked by transparent priority score · click a row to zoom to it on the map">
        <select className="input py-1.5" value={cls} onChange={(e) => setCls(e.target.value)}>
          <option value="">All defect types</option>
          {CLASSES.map((c) => <option key={c} value={c}>{CLASS_LABEL[c]}</option>)}
        </select>
        <select className="input py-1.5" value={sev} onChange={(e) => setSev(e.target.value)}>
          <option value="">All severities</option>
          {['high', 'medium', 'low'].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <Toggle checked={includeRepaired} onChange={setIncludeRepaired} label="Include repaired" />
        <a className="btn-primary" href={api.rankingCsvUrl({ include_repaired: includeRepaired || undefined })}>
          <Download size={16} /> Export CSV
        </a>
      </PageHeader>
      <ErrorBox error={error} />
      <div className="card overflow-x-auto">
        {rows === null ? (
          <Spinner label="Ranking sites…" className="justify-center py-16" />
        ) : !rows.length ? (
          <EmptyState icon={ListOrdered} title="No defect sites yet">
            Upload footage on the Upload page or seed demo data with <code className="text-accent">python scripts/seed.py</code>.
          </EmptyState>
        ) : (
          <table className="w-full min-w-[880px] text-sm">
            <thead>
              <tr className="border-b border-navy-700 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-4 py-3">Rank</th>
                <th className="px-2 py-3">Defect</th>
                <th className="px-2 py-3">Location</th>
                <th className="px-2 py-3">Type</th>
                <th className="px-2 py-3 text-center">Sightings</th>
                <th className="px-2 py-3">Last seen</th>
                <th className="px-2 py-3">Priority score</th>
                <th className="px-2 py-3">Status</th>
                <th className="px-2 py-3" />
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <Fragment key={s.id}>
                  <tr onClick={() => onZoom(s.id)} className="cursor-pointer border-b border-navy-800 transition hover:bg-navy-850">
                    <td className="px-4 py-2.5">
                      <span className={`inline-flex h-7 w-7 items-center justify-center rounded-lg text-xs font-bold ${s.rank <= 3 ? 'bg-accent text-white' : 'bg-navy-700 text-slate-300'}`}>{s.rank}</span>
                    </td>
                    <td className="px-2 py-2.5">
                      {s.thumb_url ? <img src={media(s.thumb_url)} alt="" className="h-11 w-16 rounded-md object-cover ring-1 ring-navy-600" /> : <div className="h-11 w-16 rounded-md bg-navy-800" />}
                    </td>
                    <td className="px-2 py-2.5">
                      <div className="font-medium text-slate-100">{nearestPlace(s.lat, s.lon) || 'Site #' + s.id}</div>
                      <div className="flex items-center gap-1 font-mono text-xs text-slate-500"><MapPin size={11} />{s.lat.toFixed(5)}, {s.lon.toFixed(5)} · {ROAD_LABEL[s.road_context]}</div>
                    </td>
                    <td className="px-2 py-2.5"><ClassChip cls={s.defect_class} /></td>
                    <td className="px-2 py-2.5 text-center font-semibold text-white">{s.sightings}</td>
                    <td className="px-2 py-2.5 text-slate-300">{fmtDate(s.last_seen)}</td>
                    <td className="px-2 py-2.5">
                      <div className="flex items-center gap-2"><ScoreBar score={s.score} severity={s.severity} /><SeverityBadge severity={s.status === 'repaired' ? null : s.severity} /></div>
                    </td>
                    <td className="px-2 py-2.5"><StatusBadge status={s.status} /></td>
                    <td className="px-2 py-2.5 text-right">
                      <button
                        className="btn-ghost px-2 py-1 text-xs"
                        title="Show score breakdown"
                        onClick={(e) => { e.stopPropagation(); setExpanded(expanded === s.id ? null : s.id) }}
                      >
                        <BarChart2 size={14} /> Why? <ChevronRight size={14} className={`transition ${expanded === s.id ? 'rotate-90' : ''}`} />
                      </button>
                    </td>
                  </tr>
                  {expanded === s.id && (
                    <tr className="border-b border-navy-800 bg-navy-850/60">
                      <td colSpan={9} className="px-6 py-4">
                        <div className="grid gap-6 md:grid-cols-[1fr_280px]">
                          <ScoreBreakdown components={s.components} score={s.score} severity={s.severity} height={180} />
                          <div className="space-y-2 text-xs text-slate-400">
                            <div className="text-slate-200">How this score is built</div>
                            {s.components.map((c) => (
                              <div key={c.key} className="flex justify-between gap-2">
                                <span>{c.label}</span><span className="text-slate-300">{c.detail}</span>
                              </div>
                            ))}
                            <div className="border-t border-navy-700 pt-2">Score = Σ weight × normalised value. Weights live in <code className="text-accent">backend/config.yaml</code>.</div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

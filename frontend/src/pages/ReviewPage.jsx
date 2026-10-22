import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Check, ClipboardCheck, Crosshair, Hammer, Pencil, RotateCcw, Save, X } from 'lucide-react'
import { api, media } from '../lib/api'
import { CLASSES, CLASS_LABEL, ROAD_LABEL, fmtCoord, fmtDateTime, nearestPlace } from '../lib/format'
import ScoreBreakdown from '../components/ScoreBreakdown'
import { ClassChip, EmptyState, ErrorBox, LowConfBadge, PageHeader, Segmented, SeverityBadge, Spinner, StatusBadge, Toggle } from '../components/ui'

function Toast({ msg }) {
  if (!msg) return null
  return (
    <div className="fixed bottom-6 right-6 z-[3000] rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white shadow-2xl">{msg}</div>
  )
}

/** Shows the full frame with only the selected box highlighted (drawn as an overlay). */
function FrameWithBox({ report }) {
  const [size, setSize] = useState(null)
  const [x1, y1, x2, y2] = report.bbox
  return (
    <div className="relative self-start overflow-hidden rounded-lg bg-black">
      <img src={media(report.image_url)} alt="" className="w-full" onLoad={(e) => setSize([e.target.naturalWidth, e.target.naturalHeight])} />
      {size && (
        <div className="pointer-events-none absolute rounded-sm ring-4 ring-accent/90"
          style={{ left: `${(x1 / size[0]) * 100}%`, top: `${(y1 / size[1]) * 100}%`, width: `${((x2 - x1) / size[0]) * 100}%`, height: `${((y2 - y1) / size[1]) * 100}%`, boxShadow: '0 0 0 9999px rgba(0,0,0,.35)' }} />
      )}
    </div>
  )
}

function ReportDetail({ r, onAction, busy }) {
  const [editCls, setEditCls] = useState(false)
  const [newCls, setNewCls] = useState(r.defect_class)
  const [note, setNote] = useState('')
  useEffect(() => { setEditCls(false); setNewCls(r.defect_class); setNote('') }, [r.id, r.defect_class])
  const act = (action, extra = {}) => onAction(r, { action, note: note || undefined, ...extra })

  return (
    <div className="card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-lg font-semibold text-white">Report #{r.id}</span>
          <ClassChip cls={r.defect_class} />
          {r.original_class !== r.defect_class && <span className="text-xs text-slate-400">(model said {CLASS_LABEL[r.original_class]})</span>}
          <StatusBadge status={r.status} />
          {r.low_confidence && <LowConfBadge />}
        </div>
        <span className="font-mono text-sm text-slate-300">conf {(r.confidence * 100).toFixed(1)}%</span>
      </div>

      {r.low_confidence && (
        <div className="mb-3 flex gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          <AlertTriangle size={16} className="shrink-0" />
          <span>Model confidence is below 0.5. Lighting, rain or wet surfaces, camera angle, shadows and road markings can all
            produce false detections. Please check the frame carefully before confirming.</span>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_260px]">
        <FrameWithBox report={r} />
        <div className="space-y-3 text-sm">
          {r.thumb_url && <img src={media(r.thumb_url)} alt="" className="w-full rounded-lg ring-1 ring-navy-600" />}
          <dl className="space-y-1 text-xs">
            {[
              ['Location', fmtCoord(r.lat, r.lon)],
              ['Place', nearestPlace(r.lat, r.lon) || '—'],
              ['Geotag', r.location_source],
              ['Captured', fmtDateTime(r.timestamp)],
              ['Uploader', r.uploader],
              ['Road', ROAD_LABEL[r.road_context]],
              ['Box area', `${(r.bbox_area_ratio * 100).toFixed(2)}% of frame`],
              ['Site', r.site_id ? `#${r.site_id}` : '—'],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-2"><dt className="text-slate-500">{k}</dt><dd className="text-right text-slate-200">{v}</dd></div>
            ))}
          </dl>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_260px]">
        <div>
          <div className="label mb-2">Reviewer action</div>
          <div className="flex flex-wrap gap-2">
            <button disabled={busy} className="btn bg-emerald-600 text-white hover:bg-emerald-500" onClick={() => act('confirm')}><Check size={16} /> Confirm <kbd className="ml-1 rounded bg-black/20 px-1 text-[10px]">C</kbd></button>
            <button disabled={busy} className="btn bg-rose-600 text-white hover:bg-rose-500" onClick={() => act('reject')}><X size={16} /> Reject (false positive) <kbd className="ml-1 rounded bg-black/20 px-1 text-[10px]">R</kbd></button>
            <button disabled={busy} className="btn-ghost" onClick={() => setEditCls(!editCls)}><Pencil size={16} /> Edit class</button>
            <button disabled={busy} className="btn bg-sky-700 text-white hover:bg-sky-600" onClick={() => act('repaired')}><Hammer size={16} /> Mark repaired</button>
            {r.status !== 'pending' && <button disabled={busy} className="btn-ghost" onClick={() => act('reset')}><RotateCcw size={16} /> Reset</button>}
          </div>
          {editCls && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <select className="input" value={newCls} onChange={(e) => setNewCls(e.target.value)}>
                {CLASSES.map((c) => <option key={c} value={c}>{CLASS_LABEL[c]}</option>)}
              </select>
              <button disabled={busy || newCls === r.defect_class} className="btn-primary" onClick={() => act('edit_class', { new_class: newCls })}><Save size={16} /> Save class</button>
            </div>
          )}
          <input className="input mt-3 w-full" placeholder="Optional note (e.g. 'shadow of tree', 'water-filled pothole')" value={note} onChange={(e) => setNote(e.target.value)} />
          <p className="mt-2 text-xs text-slate-500">Rejected and re-labelled detections are exported to <code className="text-accent">data/feedback/</code> in YOLO format for retraining.</p>
        </div>
        <ScoreBreakdown components={r.components} score={r.site_score} severity={r.severity} height={150} compact />
      </div>
    </div>
  )
}

function ReportQueue({ refreshKey, onChange, setToast }) {
  const [status, setStatus] = useState('pending')
  const [lowOnly, setLowOnly] = useState(false)
  const [items, setItems] = useState(null)
  const [sel, setSel] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    return api.reports({ status: status || undefined, low_confidence: lowOnly || undefined, limit: 300 })
      .then((rs) => { setItems(rs); return rs })
      .catch((e) => { setError(e); setItems([]); return [] })
  }, [status, lowOnly])

  // Keep the current selection across refreshes when it is still in the queue
  useEffect(() => {
    load().then((rs) => setSel((prev) => (rs.some((x) => x.id === prev) ? prev : rs[0]?.id ?? null)))
  }, [load, refreshKey])

  const current = items?.find((r) => r.id === sel)

  const onAction = useCallback(async (r, body) => {
    setBusy(true); setError(null)
    try {
      const res = await api.review(r.id, { reviewer: 'reviewer', ...body })
      setToast(`Report #${r.id}: ${body.action.replace('_', ' ')}${res.feedback_file ? ' · saved to feedback/' : ''}`)
      const idx = items.findIndex((x) => x.id === r.id)
      const rs = await load()
      // Auto-advance to the next item still in the queue
      const stay = rs.find((x) => x.id === r.id) // still matches the filter (e.g. "All")
      const next = stay || rs[idx] || rs[idx - 1] || rs[0]
      setSel(next?.id ?? null)
      onChange()
    } catch (e) { setError(e) } finally { setBusy(false) }
  }, [items, load, onChange, setToast])

  // Keyboard shortcuts: C = confirm, R = reject, J/K = next/prev
  useEffect(() => {
    const h = (e) => {
      if (!current || busy || ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return
      const i = items.findIndex((x) => x.id === current.id)
      if (e.key === 'c') onAction(current, { action: 'confirm' })
      else if (e.key === 'r') onAction(current, { action: 'reject' })
      else if (e.key === 'j' && items[i + 1]) setSel(items[i + 1].id)
      else if (e.key === 'k' && items[i - 1]) setSel(items[i - 1].id)
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [current, items, busy, onAction])

  return (
    <div className="grid gap-4 xl:grid-cols-[340px_1fr]">
      <div className="card flex max-h-[calc(100vh-260px)] min-h-[400px] flex-col">
        <div className="space-y-2 border-b border-navy-700 p-3">
          <select className="input w-full" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="pending">Pending review</option>
            <option value="confirmed">Confirmed</option>
            <option value="rejected">Rejected</option>
            <option value="repaired">Repaired</option>
            <option value="">All reports</option>
          </select>
          <Toggle checked={lowOnly} onChange={setLowOnly} label="Low-confidence only (< 0.5)" />
        </div>
        <div className="flex-1 overflow-y-auto">
          {items === null ? <Spinner label="Loading queue…" className="justify-center py-10" /> : !items.length ? (
            <EmptyState icon={ClipboardCheck} title="Queue is empty">Nothing matches this filter. Nice work!</EmptyState>
          ) : items.map((r) => (
            <button key={r.id} onClick={() => setSel(r.id)}
              className={`flex w-full items-center gap-3 border-b border-navy-800 px-3 py-2.5 text-left transition ${sel === r.id ? 'bg-accent/10 ring-1 ring-inset ring-accent/40' : 'hover:bg-navy-850'}`}>
              <img src={media(r.thumb_url)} alt="" className="h-12 w-12 shrink-0 rounded-md object-cover" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5"><ClassChip cls={r.defect_class} />{r.low_confidence && <AlertTriangle size={14} className="text-amber-400" />}</div>
                <div className="mt-0.5 truncate text-xs text-slate-400">#{r.id} · {(r.confidence * 100).toFixed(0)}% · {nearestPlace(r.lat, r.lon) || fmtCoord(r.lat, r.lon)}</div>
              </div>
              <SeverityBadge severity={r.severity} />
            </button>
          ))}
        </div>
        <div className="border-t border-navy-700 px-3 py-2 text-xs text-slate-500">{items?.length ?? 0} reports · keys: C confirm · R reject · J/K next/prev</div>
      </div>
      <div className="space-y-3">
        <ErrorBox error={error} />
        {current ? <ReportDetail r={current} onAction={onAction} busy={busy} /> : items?.length ? null : (
          <div className="card"><EmptyState icon={Crosshair} title="Select a report">Pick a detection from the queue to review it.</EmptyState></div>
        )}
      </div>
    </div>
  )
}

function SiteReview({ refreshKey, onChange, onZoom, setToast }) {
  const [sites, setSites] = useState(null)
  const [busy, setBusy] = useState(null)
  useEffect(() => { api.ranking({ include_repaired: true }).then(setSites).catch(() => setSites([])) }, [refreshKey])
  const act = async (s, action) => {
    setBusy(s.id)
    try {
      await api.reviewSite(s.id, { action, reviewer: 'reviewer' })
      setToast(`Site #${s.id}: ${action} applied to ${s.sightings} report(s)`)
      onChange()
    } finally { setBusy(null) }
  }
  if (sites === null) return <Spinner label="Loading sites…" />
  if (!sites.length) return <div className="card"><EmptyState title="No sites yet">Upload footage first.</EmptyState></div>
  return (
    <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
      {sites.map((s) => (
        <div key={s.id} className="card overflow-hidden">
          <div className="flex gap-3 p-3">
            <img src={media(s.thumb_url)} alt="" className="h-24 w-28 shrink-0 cursor-pointer rounded-md object-cover" onClick={() => onZoom(s.id)} title="Show on map" />
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex flex-wrap items-center gap-1.5"><span className="font-semibold text-white">#{s.id}</span><ClassChip cls={s.defect_class} /><StatusBadge status={s.status} /></div>
              <div className="text-xs text-slate-400">{nearestPlace(s.lat, s.lon) || fmtCoord(s.lat, s.lon)} · {s.sightings} sighting(s)</div>
              <SeverityBadge severity={s.status === 'repaired' ? null : s.severity} score={s.score} />
              {s.max_confidence < 0.5 && <div><LowConfBadge compact /></div>}
            </div>
          </div>
          <div className="flex border-t border-navy-700 text-xs">
            {[['confirm', 'Confirm', 'text-emerald-300'], ['reject', 'Reject', 'text-rose-300'], ['repaired', 'Repaired', 'text-sky-300']].map(([a, l, c]) => (
              <button key={a} disabled={busy === s.id} onClick={() => act(s, a)} className={`flex-1 py-2 font-medium ${c} transition hover:bg-navy-800 disabled:opacity-50`}>{l}</button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function ReviewPage({ refreshKey, onChange, onZoom }) {
  const [tab, setTab] = useState('reports')
  const [toast, setToastMsg] = useState(null)
  const setToast = useCallback((m) => { setToastMsg(m); setTimeout(() => setToastMsg(null), 2500) }, [])
  return (
    <div>
      <PageHeader title="Human-in-the-loop review" subtitle="Confirm, reject, relabel or close out detections. Corrections feed the next training run.">
        <Segmented value={tab} onChange={setTab} options={[{ value: 'reports', label: 'Report queue' }, { value: 'sites', label: 'Defect sites' }]} />
      </PageHeader>
      {tab === 'reports'
        ? <ReportQueue refreshKey={refreshKey} onChange={onChange} setToast={setToast} />
        : <SiteReview refreshKey={refreshKey} onChange={onChange} onZoom={onZoom} setToast={setToast} />}
      <Toast msg={toast} />
    </div>
  )
}

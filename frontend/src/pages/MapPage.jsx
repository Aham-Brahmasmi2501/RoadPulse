import { useEffect, useMemo, useRef, useState } from 'react'
import { Marker, Popup, useMap } from 'react-leaflet'
import { Calendar, Filter, Layers, Moon, RotateCcw } from 'lucide-react'
import { api, media } from '../lib/api'
import { CLASSES, CLASS_COLOR, CLASS_LABEL, SEV_COLOR, fmtDateTime, nearestPlace } from '../lib/format'
import BaseMap from '../components/BaseMap'
import MarkerClusterGroup, { dotIcon } from '../components/MarkerClusterGroup'
import ScoreBreakdown from '../components/ScoreBreakdown'
import { ClassChip, ErrorBox, LowConfBadge, PageHeader, Segmented, SeverityBadge, Spinner, StatusBadge, Toggle } from '../components/ui'

const markerColor = (item) => (item.status === 'repaired' ? SEV_COLOR.repaired : SEV_COLOR[item.severity] || SEV_COLOR.none)

function ReportPopup({ r }) {
  return (
    <div className="w-64">
      {r.thumb_url && <img src={media(r.thumb_url)} alt="" className="mb-2 h-32 w-full rounded-md object-cover" />}
      <div className="mb-1 flex flex-wrap items-center gap-1.5">
        <ClassChip cls={r.defect_class} />
        <SeverityBadge severity={r.severity} score={r.site_score} />
        <StatusBadge status={r.status} />
      </div>
      <div className="mb-2 space-y-0.5 text-xs text-slate-300">
        <div>Confidence <b className="text-white">{(r.confidence * 100).toFixed(0)}%</b> {r.low_confidence && <LowConfBadge compact />}</div>
        <div>{fmtDateTime(r.timestamp)} · {r.uploader}</div>
        <div className="text-slate-400">Report #{r.id} · site #{r.site_id ?? '—'} {nearestPlace(r.lat, r.lon) || ''}</div>
      </div>
      <ScoreBreakdown components={r.components} score={r.site_score} severity={r.severity} height={130} compact />
    </div>
  )
}

function SitePopup({ s }) {
  return (
    <div className="w-64">
      {s.thumb_url && <img src={media(s.thumb_url)} alt="" className="mb-2 h-32 w-full rounded-md object-cover" />}
      <div className="mb-1 flex flex-wrap items-center gap-1.5">
        <span className="text-sm font-semibold text-white">Site #{s.id}</span>
        <ClassChip cls={s.defect_class} />
        <StatusBadge status={s.status} />
      </div>
      <div className="mb-2 space-y-0.5 text-xs text-slate-300">
        <div><b className="text-white">{s.sightings}</b> sighting{s.sightings > 1 ? 's' : ''} · best conf {(s.max_confidence * 100).toFixed(0)}%</div>
        <div>First {fmtDateTime(s.first_seen)} · last {fmtDateTime(s.last_seen)}</div>
        <div className="text-slate-400">{nearestPlace(s.lat, s.lon) || `${s.lat.toFixed(5)}, ${s.lon.toFixed(5)}`}</div>
      </div>
      <ScoreBreakdown components={s.components} score={s.score} severity={s.status === 'repaired' ? 'repaired' : s.severity} height={130} compact />
    </div>
  )
}

// Fits the view to the data once, and flies to a focused site when requested.
function MapController({ points, focus, markerRefs, clusterRef, mode }) {
  const map = useMap()
  const fitted = useRef(false)
  useEffect(() => {
    if (fitted.current || !points.length || focus) return
    map.fitBounds(points, { padding: [40, 40], maxZoom: 15 })
    fitted.current = true
  }, [points, focus, map])
  useEffect(() => {
    if (!focus || mode !== 'sites') return
    const m = markerRefs.current[focus.id]
    const group = clusterRef.current
    if (!m || !group) return
    // Zoom until the marker is out of its cluster bubble (spiderfies if needed), then open it
    map.setView(m.getLatLng(), 17)
    const t = setTimeout(() => group.zoomToShowLayer(m, () => m.openPopup()), 400)
    return () => clearTimeout(t)
  }, [focus, mode, map, markerRefs, clusterRef, points])
  return null
}

function Legend() {
  return (
    <div className="pointer-events-auto absolute bottom-4 left-4 z-[500] rounded-lg bg-navy-900/95 p-3 text-xs shadow-xl ring-1 ring-navy-600">
      <div className="mb-1.5 font-semibold text-slate-200">Severity (priority score)</div>
      {[['high', 'High > 70'], ['medium', 'Medium 40-70'], ['low', 'Low < 40'], ['repaired', 'Repaired']].map(([k, l]) => (
        <div key={k} className="flex items-center gap-2 py-0.5 text-slate-300">
          <span className="h-3 w-3 rounded-full ring-2 ring-white/80" style={{ background: SEV_COLOR[k] }} /> {l}
        </div>
      ))}
    </div>
  )
}

const toggle = (arr, v) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v])

export default function MapPage({ refreshKey, focusSite }) {
  const [mode, setMode] = useState(focusSite ? 'sites' : 'reports')
  const [dark, setDark] = useState(true)
  const [classes, setClasses] = useState([])
  const [sev, setSev] = useState([])
  const [status, setStatus] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const markerRefs = useRef({})
  const clusterRef = useRef(null)

  useEffect(() => { if (focusSite) setMode('sites') }, [focusSite])

  useEffect(() => {
    setError(null)
    const params = { defect_class: classes, severity: sev, status, date_from: from, date_to: to }
    const p = mode === 'reports' ? api.reports({ ...params, located: true }) : api.sites(params)
    p.then(setItems).catch((e) => { setError(e); setItems([]) })
  }, [mode, classes, sev, status, from, to, refreshKey])

  const points = useMemo(() => (items || []).filter((i) => i.lat != null).map((i) => [i.lat, i.lon]), [items])
  const reset = () => { setClasses([]); setSev([]); setStatus(''); setFrom(''); setTo('') }

  return (
    <div className="flex h-[calc(100vh-190px)] min-h-[560px] flex-col">
      <PageHeader title="Live map" subtitle={mode === 'reports' ? 'Every crowdsourced detection, clustered by proximity' : 'De-duplicated defect sites (DBSCAN, 15 m)'}>
        <Segmented value={mode} onChange={setMode} options={[{ value: 'reports', label: 'Reports' }, { value: 'sites', label: 'Defect sites' }]} />
        <button className="btn-ghost" onClick={() => setDark(!dark)} title="Toggle dark map"><Moon size={16} /></button>
      </PageHeader>

      {/* Filters */}
      <div className="card mb-3 flex flex-wrap items-center gap-x-5 gap-y-3 px-4 py-3">
        <div className="flex items-center gap-2 text-slate-400"><Filter size={16} /></div>
        <div className="flex flex-wrap gap-1.5">
          {CLASSES.map((c) => (
            <button key={c} onClick={() => setClasses(toggle(classes, c))}
              className={`chip transition ${classes.includes(c) ? 'text-white' : 'text-slate-400 ring-1 ring-navy-600 hover:text-white'}`}
              style={classes.includes(c) ? { background: CLASS_COLOR[c] } : {}}>
              {CLASS_LABEL[c]}
            </button>
          ))}
        </div>
        <div className="flex gap-1.5">
          {['high', 'medium', 'low'].map((s) => (
            <button key={s} onClick={() => setSev(toggle(sev, s))}
              className={`chip capitalize transition ${sev.includes(s) ? 'text-white' : 'text-slate-400 ring-1 ring-navy-600 hover:text-white'}`}
              style={sev.includes(s) ? { background: SEV_COLOR[s] } : {}}>
              {s}
            </button>
          ))}
        </div>
        <select className="input py-1.5" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {['pending', 'confirmed', 'repaired', ...(mode === 'reports' ? ['rejected'] : [])].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Calendar size={16} />
          <input type="date" className="input py-1.5" value={from} onChange={(e) => setFrom(e.target.value)} />
          <span>→</span>
          <input type="date" className="input py-1.5" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
        <button className="btn-ghost py-1.5" onClick={reset}><RotateCcw size={14} /> Reset</button>
        <span className="ml-auto flex items-center gap-1 text-xs text-slate-400"><Layers size={14} /> {items ? items.length : '…'} {mode}</span>
      </div>
      <ErrorBox error={error} />

      <div className="card relative flex-1 overflow-hidden">
        {items === null && <div className="absolute inset-0 z-[600] flex items-center justify-center bg-navy-950/60"><Spinner label="Loading reports…" /></div>}
        {items && !items.length && (
          <div className="absolute left-1/2 top-6 z-[600] -translate-x-1/2 rounded-lg bg-navy-900/95 px-4 py-2 text-sm text-slate-300 ring-1 ring-navy-600">
            No {mode} match these filters. Upload footage or run <code className="text-accent">python scripts/seed.py</code>.
          </div>
        )}
        <BaseMap dark={dark} className="h-full w-full">
          <MapController points={points} focus={focusSite} markerRefs={markerRefs} clusterRef={clusterRef} mode={mode} />
          {/* key forces a fresh cluster layer whenever the data set changes */}
          <MarkerClusterGroup ref={clusterRef} key={`${mode}-${(items || []).length}-${refreshKey}`}>
            {(items || []).filter((i) => i.lat != null).map((i) =>
              mode === 'reports' ? (
                <Marker key={`r${i.id}`} position={[i.lat, i.lon]} severity={i.severity}
                  icon={dotIcon(markerColor(i), 16, i.status === 'rejected' ? '#f43f5e' : 'white')}>
                  <Popup maxWidth={300}><ReportPopup r={i} /></Popup>
                </Marker>
              ) : (
                <Marker key={`s${i.id}`} position={[i.lat, i.lon]} severity={i.status === 'repaired' ? 'low' : i.severity}
                  ref={(m) => { if (m) markerRefs.current[i.id] = m }}
                  icon={dotIcon(markerColor(i), Math.min(34, 18 + i.sightings * 2), 'white', i.sightings > 1 ? i.sightings : '')}>
                  <Popup maxWidth={300}><SitePopup s={i} /></Popup>
                </Marker>
              ),
            )}
          </MarkerClusterGroup>
        </BaseMap>
        <Legend />
      </div>
    </div>
  )
}

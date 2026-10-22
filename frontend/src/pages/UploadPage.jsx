import { useEffect, useRef, useState } from 'react'
import { Camera, CheckCircle2, Clock, FileVideo, ImageIcon, MapPin, Route, ShieldCheck, UploadCloud, X } from 'lucide-react'
import { api, media } from '../lib/api'
import { CLASS_LABEL, ROAD_LABEL, fmtCoord, fmtDateTime } from '../lib/format'
import { ClassChip, EmptyState, ErrorBox, LowConfBadge, PageHeader, Segmented, Spinner, Toggle } from '../components/ui'
import LocationPicker from '../components/LocationPicker'

const LOC_SOURCE = { exif: 'EXIF GPS', gpx: 'GPS track', manual: 'Manual pin', seed: 'Demo seed', none: 'No location' }

function Dropzone({ files, setFiles }) {
  const input = useRef(null)
  const [over, setOver] = useState(false)
  const add = (list) => {
    // Copy out of the live FileList now: the input is cleared right after this call
    const picked = Array.from(list).filter((x) => /^(image|video)\//.test(x.type) || /\.(mp4|mov|jpg|jpeg|png)$/i.test(x.name))
    setFiles((f) => [...f, ...picked])
  }
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files) }}
      onClick={() => input.current?.click()}
      className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition ${
        over ? 'border-accent bg-accent/10' : 'border-navy-600 bg-navy-850 hover:border-accent/60'
      }`}
    >
      <input ref={input} type="file" multiple accept="image/*,video/mp4,video/*" className="hidden" onChange={(e) => { add(e.target.files); e.target.value = '' }} />
      <div className="mb-3 rounded-full bg-accent/15 p-3 text-accent"><UploadCloud size={28} /></div>
      <div className="font-medium text-white">Drop dashcam / phone footage here</div>
      <div className="mt-1 text-sm text-slate-400">Images (JPG/PNG with EXIF GPS) or MP4 video · click to browse</div>
      {files.length > 0 && (
        <div className="mt-4 flex w-full flex-wrap justify-center gap-2" onClick={(e) => e.stopPropagation()}>
          {files.map((f, i) => (
            <span key={i} className="chip bg-navy-700 text-slate-200 ring-1 ring-navy-500">
              {f.type.startsWith('video') ? <FileVideo size={12} /> : <ImageIcon size={12} />}
              {f.name}
              <button onClick={() => setFiles((all) => all.filter((_, j) => j !== i))}><X size={12} /></button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function FrameCard({ frame, onOpen }) {
  return (
    <button onClick={() => onOpen(frame)} className="card group overflow-hidden text-left transition hover:ring-2 hover:ring-accent/50">
      <div className="relative aspect-video overflow-hidden bg-navy-850">
        <img src={media(frame.annotated_url)} alt="" className="h-full w-full object-cover transition group-hover:scale-[1.02]" loading="lazy" />
        <span className="absolute left-2 top-2 chip bg-black/60 text-white">
          {frame.video_time_s != null ? `t = ${frame.video_time_s.toFixed(1)}s` : 'Image'}
        </span>
        <span className={`absolute right-2 top-2 chip ${frame.detections.length ? 'bg-accent text-white' : 'bg-black/60 text-slate-300'}`}>
          {frame.detections.length} defect{frame.detections.length === 1 ? '' : 's'}
        </span>
      </div>
      <div className="space-y-1.5 p-3">
        <div className="flex flex-wrap gap-1">
          {frame.detections.slice(0, 4).map((d) => <ClassChip key={d.report_id} cls={d.class} />)}
          {frame.detections.length > 4 && <span className="chip bg-navy-700 text-slate-300">+{frame.detections.length - 4}</span>}
          {frame.detections.some((d) => d.low_confidence) && <LowConfBadge compact />}
        </div>
        <div className="flex items-center gap-1 text-xs text-slate-400">
          <MapPin size={12} /> {fmtCoord(frame.lat, frame.lon)} · {LOC_SOURCE[frame.location_source]}
        </div>
      </div>
    </button>
  )
}

function Lightbox({ frame, onClose }) {
  useEffect(() => {
    const h = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  if (!frame) return null
  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center bg-black/80 p-4" onClick={onClose}>
      <div className="card max-h-full w-full max-w-5xl overflow-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-navy-700 px-4 py-3">
          <div className="text-sm text-slate-300">
            Frame #{frame.frame_index} · {fmtDateTime(frame.timestamp)} · {fmtCoord(frame.lat, frame.lon)}
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X /></button>
        </div>
        <img src={media(frame.annotated_url)} alt="" className="w-full" />
        <div className="grid gap-2 p-4 sm:grid-cols-2">
          {frame.detections.map((d) => (
            <div key={d.report_id} className="flex items-center justify-between rounded-lg bg-navy-850 px-3 py-2 text-sm">
              <span className="flex items-center gap-2"><ClassChip cls={d.class} /> <span className="text-slate-400">report #{d.report_id}</span></span>
              <span className="flex items-center gap-2">
                {d.low_confidence && <LowConfBadge compact />}
                <span className="font-mono text-slate-200">{(d.confidence * 100).toFixed(0)}%</span>
              </span>
            </div>
          ))}
          {!frame.detections.length && <div className="text-sm text-slate-400">No defects detected in this frame.</div>}
        </div>
      </div>
    </div>
  )
}

function UploadResult({ up, onLocated }) {
  const [showAll, setShowAll] = useState(false)
  const [open, setOpen] = useState(null)
  const [busy, setBusy] = useState(false)
  const withDet = up.frames.filter((f) => f.detections.length)
  const frames = showAll ? up.frames : withDet
  const classes = {}
  up.frames.forEach((f) => f.detections.forEach((d) => { classes[d.class] = (classes[d.class] || 0) + 1 }))
  const confirm = async ([lat, lon]) => {
    setBusy(true)
    try { onLocated(await api.setUploadLocation(up.id, lat, lon)) } finally { setBusy(false) }
  }
  return (
    <div className="card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-white">
            {up.kind === 'video' ? <FileVideo size={18} className="text-accent" /> : <Camera size={18} className="text-accent" />}
            {up.filename}
          </div>
          <div className="mt-0.5 text-xs text-slate-400">
            {up.kind === 'video' ? `${up.frame_count} frames sampled` : '1 image'} · {up.detection_count} detection{up.detection_count === 1 ? '' : 's'} · {ROAD_LABEL[up.road_context]} ·{' '}
            {up.blur ? 'faces/plates blurred' : 'privacy blur off'} · by {up.uploader}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {Object.entries(classes).map(([c, n]) => (
            <span key={c} className="chip bg-navy-800 text-slate-300 ring-1 ring-navy-600">{n}× {CLASS_LABEL[c]}</span>
          ))}
          {up.frame_count > withDet.length && <Toggle checked={showAll} onChange={setShowAll} label="Show empty frames" />}
        </div>
      </div>
      {up.needs_location && <div className="mb-4"><LocationPicker onConfirm={confirm} busy={busy} /></div>}
      {frames.length ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {frames.map((f) => <FrameCard key={f.id} frame={f} onOpen={setOpen} />)}
        </div>
      ) : (
        <EmptyState icon={CheckCircle2} title="No road defects detected">
          The model didn't find potholes or cracks above the confidence threshold. Try another clip or lower
          <code className="mx-1 text-accent">conf_threshold</code> in backend/config.yaml.
        </EmptyState>
      )}
      <Lightbox frame={open} onClose={() => setOpen(null)} />
    </div>
  )
}

export default function UploadPage({ cfg, onChange, onGoMap }) {
  const [files, setFiles] = useState([])
  const [track, setTrack] = useState(null)
  const [uploader, setUploader] = useState('citizen-app')
  const [road, setRoad] = useState('main_road')
  const [blur, setBlur] = useState(true)
  const [every, setEvery] = useState(1)
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState(null)
  const [results, setResults] = useState([])
  const [recent, setRecent] = useState([])

  useEffect(() => { api.uploads().then(setRecent).catch(() => {}) }, [])
  useEffect(() => { if (cfg) { setBlur(cfg.privacy.blur_default); setEvery(cfg.video.sample_every_sec) } }, [cfg])
  useEffect(() => {
    if (!busy) return
    const t0 = Date.now()
    const id = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 500)
    return () => clearInterval(id)
  }, [busy])

  const hasVideo = files.some((f) => f.type.startsWith('video') || /\.(mp4|mov)$/i.test(f.name))

  const submit = async () => {
    setBusy(true); setError(null); setElapsed(0)
    const fd = new FormData()
    files.forEach((f) => fd.append('files', f))
    if (track) fd.append('gps_track', track)
    fd.append('uploader', uploader || 'anonymous')
    fd.append('road_context', road)
    fd.append('blur', blur)
    fd.append('sample_every', every)
    try {
      const res = await api.upload(fd)
      setResults(res.uploads)
      setFiles([]); setTrack(null)
      onChange()
      api.uploads().then(setRecent).catch(() => {})
    } catch (e) { setError(e) } finally { setBusy(false) }
  }

  const replace = (res) => {
    setResults((rs) => rs.map((u) => (u.id === res.upload.id ? res.upload : u)))
    onChange()
  }

  return (
    <div>
      <PageHeader title="Upload footage" subtitle="Detect potholes and cracks in dashcam or smartphone images and video">
        {results.length > 0 && <button className="btn-ghost" onClick={onGoMap}><MapPin size={16} /> View on map</button>}
      </PageHeader>

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2"><Dropzone files={files} setFiles={setFiles} /></div>
        <div className="card space-y-4 p-4">
          <div>
            <div className="label mb-1.5">Road context</div>
            <Segmented value={road} onChange={setRoad} options={Object.entries(ROAD_LABEL).map(([value, label]) => ({ value, label }))} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="label mb-1.5">Uploader</div>
              <input className="input w-full" value={uploader} onChange={(e) => setUploader(e.target.value)} />
            </div>
            <div>
              <div className="label mb-1.5">Video: 1 frame every</div>
              <div className="flex items-center gap-2">
                <input type="number" min="0.2" step="0.1" className="input w-full" value={every} onChange={(e) => setEvery(e.target.value)} />
                <span className="text-sm text-slate-400">s</span>
              </div>
            </div>
          </div>
          <div>
            <div className="label mb-1.5 flex items-center gap-1"><Route size={12} /> GPS track for video (GPX / CSV)</div>
            <label className="input flex cursor-pointer items-center justify-between">
              <span className={track ? 'text-slate-100' : 'text-slate-500'}>{track ? track.name : 'Optional · time, lat, lon'}</span>
              <input type="file" accept=".gpx,.csv" className="hidden" onChange={(e) => setTrack(e.target.files[0] || null)} />
              {track && <button onClick={(e) => { e.preventDefault(); setTrack(null) }}><X size={14} /></button>}
            </label>
          </div>
          <div className="flex items-center justify-between">
            <Toggle checked={blur} onChange={setBlur} label={<span className="flex items-center gap-1"><ShieldCheck size={14} /> Blur faces & number plates</span>} />
          </div>
          <button className="btn-primary w-full py-2.5" disabled={!files.length || busy} onClick={submit}>
            {busy ? 'Analysing…' : `Run detection${files.length ? ` on ${files.length} file${files.length > 1 ? 's' : ''}` : ''}`}
          </button>
          {hasVideo && !track && <p className="text-xs text-slate-500">No GPS track: you'll be asked to pin the location on a map.</p>}
        </div>
      </div>

      <div className="mt-5 space-y-4">
        {busy && (
          <div className="card flex flex-col items-center gap-3 py-10">
            <Spinner label={hasVideo ? 'Sampling frames and running YOLOv8 on each…' : 'Running YOLOv8 detection…'} />
            <div className="h-1.5 w-64 overflow-hidden rounded-full bg-navy-700">
              <div className="h-full w-1/3 animate-[pulse_1s_ease-in-out_infinite] rounded-full bg-accent" style={{ marginLeft: `${(elapsed * 13) % 70}%` }} />
            </div>
            <div className="flex items-center gap-1 text-xs text-slate-500"><Clock size={12} /> {elapsed}s · CPU inference takes ~0.3-0.6 s per frame</div>
          </div>
        )}
        <ErrorBox error={error} />
        {!busy && results.map((u) => <UploadResult key={u.id} up={u} onLocated={replace} />)}
        {!busy && !results.length && (
          <div className="card p-4">
            <div className="mb-3 text-sm font-semibold text-white">Recent uploads</div>
            {recent.length ? (
              <div className="divide-y divide-navy-700">
                {recent.map((u) => (
                  <button key={u.id} onClick={() => setResults([u])} className="flex w-full items-center justify-between gap-3 py-2.5 text-left text-sm hover:text-accent">
                    <span className="flex min-w-0 items-center gap-2">
                      {u.kind === 'video' ? <FileVideo size={16} className="shrink-0 text-slate-400" /> : <ImageIcon size={16} className="shrink-0 text-slate-400" />}
                      <span className="truncate">{u.filename}</span>
                      {u.needs_location && <span className="chip bg-amber-500/15 text-amber-300">needs location</span>}
                    </span>
                    <span className="shrink-0 text-xs text-slate-400">{u.detection_count} detection{u.detection_count === 1 ? '' : 's'} · {u.uploader} · {fmtDateTime(u.created_at)}</span>
                  </button>
                ))}
              </div>
            ) : (
              <EmptyState icon={UploadCloud} title="No uploads yet">
                Try the files in <code className="text-accent">sample_data/</code>: GPS-tagged JPGs, a pothole video and its GPX track.
              </EmptyState>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

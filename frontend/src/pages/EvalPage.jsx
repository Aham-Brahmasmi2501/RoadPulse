import { useEffect, useState } from 'react'
import { BarChart3, FlaskConical, RefreshCw } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, media } from '../lib/api'
import { CLASS_LABEL } from '../lib/format'
import { EmptyState, ErrorBox, PageHeader, Spinner } from '../components/ui'

function Metric({ label, value, hint, color = '#f97316' }) {
  return (
    <div className="card p-4">
      <div className="label">{label}</div>
      <div className="mt-1 text-3xl font-bold" style={{ color }}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-500">{hint}</div>}
    </div>
  )
}

function ConfusionMatrix({ labels, matrix }) {
  const max = Math.max(1, ...matrix.flat())
  const short = (l) => (l === 'background' ? 'backgr.' : CLASS_LABEL[l] || l)
  return (
    <div className="overflow-x-auto">
      <table className="mx-auto border-separate border-spacing-1 text-xs">
        <thead>
          <tr>
            <th className="p-1 text-right text-[10px] font-normal text-slate-500">pred ↓ / true →</th>
            {labels.map((l) => <th key={l} className="w-20 p-1 text-center font-medium text-slate-300">{short(l)}</th>)}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={i}>
              <th className="p-1 pr-2 text-right font-medium text-slate-300">{short(labels[i])}</th>
              {row.map((v, j) => {
                const a = v / max
                const diag = i === j && i < labels.length - 1
                return (
                  <td key={j} className="h-12 w-20 rounded-md text-center font-mono text-sm"
                    style={{ background: v ? (diag ? `rgba(34,197,94,${0.15 + a * 0.75})` : `rgba(249,115,22,${0.12 + a * 0.7})`) : '#0f1a30', color: v ? '#fff' : '#475569' }}>
                    {v}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-center text-xs text-slate-500">Green = correct class; orange = confusion, false positive (background column) or miss (background row). IoU ≥ 0.5.</p>
    </div>
  )
}

function Samples({ title, items, tone }) {
  return (
    <div className="card p-4">
      <div className={`mb-3 text-sm font-semibold ${tone}`}>{title}</div>
      {items.length ? (
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-3">
          {items.map((s) => (
            <a key={s.image} href={media(s.image)} target="_blank" rel="noreferrer" className="group overflow-hidden rounded-lg ring-1 ring-navy-600">
              <img src={media(s.image)} alt={s.name} className="aspect-square w-full object-cover transition group-hover:scale-105" />
            </a>
          ))}
        </div>
      ) : <div className="text-sm text-slate-500">None at this threshold.</div>}
    </div>
  )
}

export default function EvalPage() {
  const [res, setRes] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const run = (refresh) => {
    setLoading(true); setError(null)
    api.evaluate(refresh).then(setRes).catch(setError).finally(() => setLoading(false))
  }
  useEffect(() => run(false), [])

  const chartData = (res?.per_class || []).filter((c) => c.gt > 0 || c.fp > 0).map((c) => ({
    name: CLASS_LABEL[c.class], Precision: c.precision ?? 0, Recall: c.recall ?? 0, 'AP@0.5': c.ap50 ?? 0,
  }))

  return (
    <div>
      <PageHeader title="Model evaluation" subtitle="Detector performance on the labelled test set in data/eval (images + YOLO labels)">
        <button className="btn-primary" disabled={loading} onClick={() => run(true)}>
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> {loading ? 'Evaluating…' : 'Re-run evaluation'}
        </button>
      </PageHeader>
      <ErrorBox error={error} />
      {loading && !res && <div className="card py-16"><Spinner label="Running the model on the test set…" className="justify-center" /></div>}
      {res && !res.available && (
        <div className="card"><EmptyState icon={FlaskConical} title="No evaluation set found">
          {res.message} <br />e.g. <code className="text-accent">python scripts/prepare_eval.py --crack-seg</code>
        </EmptyState></div>
      )}
      {res?.available && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Metric label="Precision" value={res.precision.toFixed(3)} hint={`at conf ≥ ${res.conf_threshold}`} color="#38bdf8" />
            <Metric label="Recall" value={res.recall.toFixed(3)} hint={`IoU ≥ ${res.iou_threshold}`} color="#a78bfa" />
            <Metric label="mAP@0.5" value={res.map50.toFixed(3)} hint="mean over classes with ground truth" color="#f97316" />
            <Metric label="Test images" value={res.images} hint={`${res.seconds}s · ${res.generated_at}`} color="#22c55e" />
          </div>
          {res.source && <div className="rounded-lg border border-navy-600 bg-navy-850 px-4 py-3 text-xs leading-relaxed text-slate-400"><b className="text-slate-200">Dataset · </b>{res.source}<br /><b className="text-slate-200">Model · </b>{res.model}</div>}
          <div className="grid gap-4 xl:grid-cols-2">
            <div className="card p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white"><BarChart3 size={16} className="text-accent" /> Per-class metrics</div>
              <table className="mb-4 w-full text-sm">
                <thead><tr className="text-left text-xs uppercase text-slate-400"><th className="py-1">Class</th><th>GT</th><th>TP</th><th>FP</th><th>Prec.</th><th>Recall</th><th>AP@0.5</th></tr></thead>
                <tbody>
                  {res.per_class.map((c) => (
                    <tr key={c.class} className="border-t border-navy-800 text-slate-200">
                      <td className="py-1.5">{CLASS_LABEL[c.class]}</td><td>{c.gt}</td><td>{c.tp}</td><td>{c.fp}</td>
                      <td>{c.precision ?? '—'}</td><td>{c.recall ?? '—'}</td><td className="font-semibold">{c.ap50 ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {chartData.length > 0 && (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={chartData}>
                    <CartesianGrid stroke="#1c2b4a" vertical={false} />
                    <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis domain={[0, 1]} tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ background: '#0b1324', border: '1px solid #2a3b5f', borderRadius: 8 }} cursor={{ fill: 'rgba(255,255,255,.04)' }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="Precision" fill="#38bdf8" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="Recall" fill="#a78bfa" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="AP@0.5" fill="#f97316" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
            <div className="card p-4">
              <div className="mb-3 text-sm font-semibold text-white">Confusion matrix</div>
              <ConfusionMatrix labels={res.confusion.labels} matrix={res.confusion.matrix} />
            </div>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <Samples title="Sample true positives" items={res.samples.true_positives} tone="text-emerald-300" />
            <Samples title="Sample false positives / misses" items={res.samples.false_positives} tone="text-rose-300" />
          </div>
          <p className="text-xs text-slate-500">White boxes = ground truth; coloured = correct predictions (TP); red = false positives.</p>
        </div>
      )}
    </div>
  )
}

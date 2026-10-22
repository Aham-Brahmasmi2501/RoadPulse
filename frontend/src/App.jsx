import { useEffect, useState } from 'react'
import { BarChart3, ClipboardCheck, ListOrdered, Map, Menu, UploadCloud, X } from 'lucide-react'
import StatCards from './components/StatCards'
import UploadPage from './pages/UploadPage'
import MapPage from './pages/MapPage'
import RankingPage from './pages/RankingPage'
import ReviewPage from './pages/ReviewPage'
import EvalPage from './pages/EvalPage'
import { api } from './lib/api'

const NAV = [
  { id: 'upload', label: 'Upload', icon: UploadCloud },
  { id: 'map', label: 'Live Map', icon: Map },
  { id: 'ranking', label: 'Inspection List', icon: ListOrdered },
  { id: 'review', label: 'Review', icon: ClipboardCheck },
  { id: 'eval', label: 'Evaluation', icon: BarChart3 },
]

function Logo() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <svg viewBox="0 0 32 32" className="h-8 w-8">
        <rect width="32" height="32" rx="8" fill="#13203b" />
        <path d="M4 18h6l3-8 5 14 3-6h7" fill="none" stroke="#f97316" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <div>
        <div className="text-base font-bold tracking-tight text-white">RoadPulse</div>
        <div className="-mt-0.5 text-[10px] uppercase tracking-widest text-slate-500">Road distress mapper</div>
      </div>
    </div>
  )
}

export default function App() {
  // Simple hash routing keeps the app dependency-free and deep-linkable.
  const initial = window.location.hash.replace('#/', '') || 'upload'
  const [page, setPage] = useState(NAV.some((n) => n.id === initial) ? initial : 'upload')
  const [refreshKey, setRefreshKey] = useState(0)
  const [focusSite, setFocusSite] = useState(null)
  const [cfg, setCfg] = useState(null)
  const [apiDown, setApiDown] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    api.config().then((c) => { setCfg(c); setApiDown(false) }).catch(() => setApiDown(true))
  }, [refreshKey])
  useEffect(() => { window.location.hash = `/${page}` }, [page])
  useEffect(() => {
    // Back/forward buttons and pasted links
    const onHash = () => {
      const h = window.location.hash.replace('#/', '')
      if (NAV.some((n) => n.id === h)) setPage(h)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const refresh = () => setRefreshKey((k) => k + 1)
  const go = (p) => { setPage(p); setMenuOpen(false) }
  const zoomToSite = (id) => { setFocusSite({ id, t: Date.now() }); go('map') }

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className={`fixed inset-y-0 left-0 z-[1100] w-60 shrink-0 border-r border-navy-700/70 bg-navy-900 p-4 transition-transform lg:static lg:translate-x-0 ${menuOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="mb-8 flex items-center justify-between">
          <Logo />
          <button className="text-slate-400 lg:hidden" onClick={() => setMenuOpen(false)}><X size={20} /></button>
        </div>
        <nav className="space-y-1">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => go(id)}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                page === id ? 'bg-accent/15 text-accent ring-1 ring-accent/30' : 'text-slate-300 hover:bg-navy-800 hover:text-white'
              }`}
            >
              <Icon size={18} /> {label}
            </button>
          ))}
        </nav>
        <div className="absolute bottom-4 left-4 right-4 rounded-lg bg-navy-850 p-3 text-xs text-slate-400 ring-1 ring-navy-700">
          <div className="mb-1 flex items-center gap-1.5 font-medium text-slate-300">
            <span className={`h-2 w-2 rounded-full ${apiDown ? 'bg-rose-500' : 'bg-emerald-500'}`} />
            {apiDown ? 'API offline' : 'API connected'}
          </div>
          {cfg && <div className="break-words leading-snug">Model: {cfg.model.weights}</div>}
          {apiDown && <div>Start the backend on :8000</div>}
        </div>
      </aside>

      {/* Main column */}
      <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
        <div className="sticky top-0 z-[1000] border-b border-navy-700/60 bg-navy-950/90 px-4 py-4 backdrop-blur lg:px-6">
          <div className="mb-3 flex items-center gap-3 lg:hidden">
            <button className="text-slate-300" onClick={() => setMenuOpen(true)}><Menu /></button>
            <Logo />
          </div>
          <StatCards refreshKey={refreshKey} />
        </div>
        <div className="flex-1 px-4 py-5 lg:px-6">
          {page === 'upload' && <UploadPage cfg={cfg} onChange={refresh} onGoMap={() => go('map')} />}
          {page === 'map' && <MapPage cfg={cfg} refreshKey={refreshKey} focusSite={focusSite} />}
          {page === 'ranking' && <RankingPage refreshKey={refreshKey} onZoom={zoomToSite} />}
          {page === 'review' && <ReviewPage cfg={cfg} refreshKey={refreshKey} onChange={refresh} onZoom={zoomToSite} />}
          {page === 'eval' && <EvalPage />}
        </div>
      </main>
    </div>
  )
}

// Shared labels, colours and formatting helpers.
export const CLASSES = ['pothole', 'crack', 'alligator_crack', 'patch_damage']
export const CLASS_LABEL = { pothole: 'Pothole', crack: 'Crack', alligator_crack: 'Alligator crack', patch_damage: 'Patch damage' }
export const CLASS_COLOR = { pothole: '#f97316', crack: '#38bdf8', alligator_crack: '#a78bfa', patch_damage: '#facc15' }
export const SEV_COLOR = { low: '#22c55e', medium: '#f59e0b', high: '#ef4444', repaired: '#64748b', none: '#64748b' }
export const SEV_LABEL = { low: 'Low', medium: 'Medium', high: 'High' }
export const STATUS_STYLE = {
  pending: 'bg-slate-500/15 text-slate-300 ring-1 ring-slate-500/30',
  confirmed: 'bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30',
  rejected: 'bg-rose-500/15 text-rose-300 ring-1 ring-rose-500/30',
  repaired: 'bg-sky-500/15 text-sky-300 ring-1 ring-sky-500/30',
}
export const ROAD_LABEL = { highway: 'Highway', main_road: 'Main road', local_street: 'Local street' }

export const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' }) : '—')
export const fmtDateTime = (iso) =>
  iso ? new Date(iso).toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'
export const fmtPct = (v) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(1)}%`)
export const fmtCoord = (lat, lon) => (lat == null ? 'No location' : `${lat.toFixed(5)}, ${lon.toFixed(5)}`)

// A few Ahmedabad landmarks so locations read like places, not just coordinates.
const LOCALITIES = [
  ['Chandkheda', 23.1095, 72.5875], ['Visat Circle', 23.0937, 72.5858], ['Motera', 23.0918, 72.5966],
  ['Gota, SG Highway', 23.0989, 72.5395], ['Vaishnodevi Circle', 23.1335, 72.5400], ['Sola, SG Highway', 23.0705, 72.5178],
  ['Thaltej, SG Highway', 23.0496, 72.5117], ['Bodakdev, SG Highway', 23.0405, 72.5125], ['Sabarmati', 23.0820, 72.5880],
  ['Science City Rd', 23.0780, 72.4950], ['Zundal', 23.1220, 72.5800], ['Chandkheda Rly Stn', 23.1150, 72.5970],
  ['New CG Road', 23.1085, 72.5932], ['ONGC Colony', 23.1060, 72.5890],
]
export function nearestPlace(lat, lon) {
  if (lat == null) return null
  let best = null
  let bestD = Infinity
  for (const [name, la, lo] of LOCALITIES) {
    const d = Math.hypot((la - lat) * 111, (lo - lon) * 102)
    if (d < bestD) { bestD = d; best = name }
  }
  return bestD < 2.5 ? `near ${best}` : null
}

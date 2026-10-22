// Click-to-place map used when an upload has no GPS (no EXIF and no track).
import { useState } from 'react'
import { Marker, useMapEvents } from 'react-leaflet'
import { MapPinned } from 'lucide-react'
import BaseMap from './BaseMap'
import { dotIcon } from './MarkerClusterGroup'

function ClickHandler({ onPick }) {
  useMapEvents({ click: (e) => onPick([e.latlng.lat, e.latlng.lng]) })
  return null
}

export default function LocationPicker({ initial, onConfirm, busy }) {
  const [pos, setPos] = useState(initial || null)
  return (
    <div className="overflow-hidden rounded-xl border border-amber-500/40 bg-amber-500/5">
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
        <div className="flex items-center gap-2 text-sm text-amber-200">
          <MapPinned size={18} />
          {pos
            ? <>Pin at <b className="font-mono">{pos[0].toFixed(5)}, {pos[1].toFixed(5)}</b> - confirm to geotag these reports.</>
            : <>No GPS found in this upload. <b>Click on the map</b> where the footage was captured.</>}
        </div>
        <button className="btn-primary" disabled={!pos || busy} onClick={() => onConfirm(pos)}>
          {busy ? 'Saving…' : 'Confirm location'}
        </button>
      </div>
      <BaseMap className="h-72 w-full" zoom={13} center={initial || undefined}>
        <ClickHandler onPick={setPos} />
        {pos && <Marker position={pos} icon={dotIcon('#f97316', 22)} />}
      </BaseMap>
    </div>
  )
}

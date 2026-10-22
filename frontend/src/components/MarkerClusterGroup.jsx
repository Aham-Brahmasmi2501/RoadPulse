// react-leaflet wrapper for leaflet.markercluster. Children are normal
// <Marker> elements; cluster bubbles are coloured by the worst severity inside.
import { createPathComponent } from '@react-leaflet/core'
import L from '../lib/leaflet-setup'
import 'leaflet.markercluster'
import { SEV_COLOR } from '../lib/format'

const RANK = { high: 3, medium: 2, low: 1 }

function clusterIcon(cluster) {
  const markers = cluster.getAllChildMarkers()
  let worst = 'low'
  for (const m of markers) {
    const s = m.options.severity
    if ((RANK[s] || 0) > (RANK[worst] || 0)) worst = s
  }
  const n = cluster.getChildCount()
  const size = n < 10 ? 34 : n < 30 ? 42 : 50
  return L.divIcon({
    html: `<div class="rp-cluster" style="width:${size}px;height:${size}px;background:${SEV_COLOR[worst]}">${n}</div>`,
    className: '',
    iconSize: [size, size],
  })
}

const MarkerClusterGroup = createPathComponent(({ children: _children, ...props }, ctx) => {
  const instance = L.markerClusterGroup({
    showCoverageOnHover: false,
    maxClusterRadius: 45,
    spiderfyOnMaxZoom: true,
    iconCreateFunction: clusterIcon,
    ...props,
  })
  return { instance, context: { ...ctx, layerContainer: instance } }
})

export default MarkerClusterGroup

// Round marker icon, size scales with sightings for site view.
export function dotIcon(color, size = 16, ring = 'white', label = '') {
  return L.divIcon({
    html: `<div class="rp-marker" style="width:${size}px;height:${size}px;background:${color};border-color:${ring};display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:white">${label}</div>`,
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  })
}

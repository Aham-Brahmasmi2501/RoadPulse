// MapContainer pre-configured with OpenStreetMap tiles (optionally dark-filtered).
import { MapContainer, TileLayer } from 'react-leaflet'

export const AHMEDABAD = [23.085, 72.555]
// Standard OpenStreetMap tiles; override with VITE_TILE_URL for a self-hosted / offline tile server.
const TILE_URL = import.meta.env.VITE_TILE_URL || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'

export default function BaseMap({ center = AHMEDABAD, zoom = 13, dark = true, children, className = '', ...rest }) {
  return (
    <MapContainer center={center} zoom={zoom} className={`${dark ? 'dark-tiles' : ''} ${className}`} scrollWheelZoom {...rest}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url={TILE_URL}
        maxZoom={19}
      />
      {children}
    </MapContainer>
  )
}

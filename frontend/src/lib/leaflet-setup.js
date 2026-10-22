// leaflet.markercluster is a UMD plugin that expects a global `L`.
// Importing this module first guarantees the global exists.
import L from 'leaflet'

window.L = window.L || L
export default L

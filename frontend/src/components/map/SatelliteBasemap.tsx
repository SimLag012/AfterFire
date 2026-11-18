import { useState } from 'react';
import { TileLayer } from 'react-leaflet';

export const SATELLITE_TILES = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

/** Geographic context only: acquisition dates vary and are independent of scientific overlays. */
export function SatelliteBasemap({labels=false,terrain=false}: {labels?:boolean;terrain?:boolean}) {
  const [unavailable, setUnavailable] = useState(false);
  return <>
    <TileLayer key={terrain ? 'terrain' : 'satellite'} url={terrain ? 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Terrain_Base/MapServer/tile/{z}/{y}/{x}' : SATELLITE_TILES} maxNativeZoom={19} maxZoom={22}
      attribution='Imagery &copy; Esri, Vantor, Earthstar Geographics, GIS User Community · <a href="https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9">Sources &amp; terms</a> · dates vary'
      eventHandlers={{tileerror: () => setUnavailable(true), tileload: () => setUnavailable(false)}} />
    {labels && <TileLayer url="https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}" maxZoom={22} attribution="Labels © Esri" />}
    {unavailable && <div role="alert" className="absolute left-12 right-12 top-2 z-[1000] rounded bg-dark-950/95 p-2 text-xs text-amber-200">
      Satellite imagery is temporarily unavailable for some tiles. Check your connection or zoom out.
    </div>}
  </>;
}

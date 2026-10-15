import L from "leaflet";
import { useEffect, useMemo } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CircleMarker, MapContainer, Marker, TileLayer, Tooltip, useMap } from "react-leaflet";
import { Home } from "lucide-react";
import type { Poi } from "@/lib/api";
import { fmtDist } from "@/lib/format";
import { poiColor, poiMeta } from "../poi";
import { useTheme } from "../theme";

export interface MapCircle { lat: number; lon: number; radius: number; color: string; label: string }
export interface MapProps {
  center: [number, number];
  zoom?: number;
  home?: { lat: number; lon: number; label: string } | null;
  pois?: Poi[];
  circles?: MapCircle[];
}

function Fit({ pts }: { pts: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (pts.length > 1) map.fitBounds(L.latLngBounds(pts), { padding: [40, 40], maxZoom: 16 });
    else if (pts.length === 1) map.setView(pts[0], 15);
  }, [map, JSON.stringify(pts)]);
  return null;
}

const icon = (html: string, cls: string, size: number) =>
  L.divIcon({ html, className: "", iconSize: [size, size], iconAnchor: [size / 2, size / 2] });

export default function LeafletMap({ center, zoom = 12, home, pois = [], circles = [] }: MapProps) {
  const { theme } = useTheme();
  const tiles = `https://{s}.basemaps.cartocdn.com/${theme === "dark" ? "dark_all" : "light_all"}/{z}/{x}/{y}{r}.png`;
  const pts = useMemo<[number, number][]>(
    () => (home ? [[home.lat, home.lon] as [number, number], ...pois.map((p) => [p.lat, p.lon] as [number, number])] : []),
    [home, pois],
  );
  return (
    <MapContainer center={center} zoom={zoom} scrollWheelZoom={false} className="h-full w-full">
      <TileLayer key={theme} url={tiles} attribution='&copy; OpenStreetMap &copy; CARTO' />
      {pts.length > 0 && <Fit pts={pts} />}
      {circles.map((c) => (
        <CircleMarker key={c.label} center={[c.lat, c.lon]} radius={c.radius} pathOptions={{ color: c.color, fillColor: c.color, fillOpacity: 0.55, weight: 1 }}>
          <Tooltip>{c.label}</Tooltip>
        </CircleMarker>
      ))}
      {pois.map((p, i) => {
        const m = poiMeta(p.categoria);
        const Icon = m.icon;
        const html = `<div class="poi-pin" style="background:${poiColor(p.categoria)}">${renderToStaticMarkup(<Icon size={13} />)}</div>`;
        return (
          <Marker key={i} position={[p.lat, p.lon]} icon={icon(html, "", 26)}>
            <Tooltip>
              <strong>{m.label}</strong> · {p.nome ?? "Sem nome"} · {fmtDist(p.distancia_m)}
            </Tooltip>
          </Marker>
        );
      })}
      {home && (
        <Marker
          position={[home.lat, home.lon]}
          zIndexOffset={1000}
          icon={icon(`<div class="poi-pin home-pin">${renderToStaticMarkup(<Home size={16} />)}</div>`, "", 34)}
        >
          <Tooltip>{home.label}</Tooltip>
        </Marker>
      )}
    </MapContainer>
  );
}

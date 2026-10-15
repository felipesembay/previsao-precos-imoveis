import { Building2, Cross, GraduationCap, Pill, School, ShieldCheck, ShoppingCart, TrainFront, Trees, type LucideIcon } from "lucide-react";
import type { Poi } from "@/lib/api";
import { fmtDist } from "@/lib/format";

export const POI_META: Record<string, { label: string; icon: LucideIcon }> = {
  metro: { label: "Metrô", icon: TrainFront },
  escola_publica: { label: "Escola pública", icon: School },
  escola_privada: { label: "Escola privada", icon: GraduationCap },
  hospital: { label: "Hospital", icon: Cross },
  farmacia: { label: "Farmácia", icon: Pill },
  mercado: { label: "Mercado", icon: ShoppingCart },
  parque: { label: "Parque", icon: Trees },
  delegacia: { label: "Delegacia", icon: ShieldCheck },
};
export const poiMeta = (c: string) => POI_META[c] ?? { label: c, icon: Building2 };
export const poiColor = (c: string) => (POI_META[c] ? `var(--poi-${c})` : "var(--muted-foreground)");

export function PoiList({ pois }: { pois: Poi[] }) {
  const grupos = Object.keys(POI_META)
    .map((cat) => ({ cat, itens: pois.filter((p) => p.categoria === cat) }))
    .filter((g) => g.itens.length);
  if (!pois.length) return <p className="text-sm text-muted-foreground">Nenhum ponto de interesse encontrado num raio de 2 km.</p>;
  return (
    <ul className="divide-y">
      {grupos.map(({ cat, itens }) => {
        const m = poiMeta(cat);
        const Icon = m.icon;
        const maisPerto = itens[0]!;
        return (
          <li key={cat} className="flex items-center gap-3 py-2.5">
            <span className="poi-pin shrink-0" style={{ background: poiColor(cat) }}>
              <Icon className="size-3.5" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium">{m.label}</div>
              <div className="truncate text-xs text-muted-foreground">
                {maisPerto.nome ?? "Sem nome"}
                {itens.length > 1 && ` · +${itens.length - 1}`}
              </div>
            </div>
            <span className="num text-sm font-medium">{fmtDist(maisPerto.distancia_m)}</span>
          </li>
        );
      })}
    </ul>
  );
}

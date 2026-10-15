import { Info, MapPin } from "lucide-react";
import type { ReactNode } from "react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import type { Localizacao, ModeloRef, Poi } from "@/lib/api";
import { MapView } from "./map/MapView";
import { PoiList } from "./poi";
import { EmptyState } from "./states";
import { Link } from "@tanstack/react-router";

export function NumField({ id, label, value, onChange, min = 0, suffix }: { id: string; label: string; value: number; onChange: (v: number) => void; min?: number; suffix?: string }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs text-muted-foreground">{label}</Label>
      <div className="relative">
        <Input id={id} type="number" inputMode="numeric" min={min} value={Number.isNaN(value) ? "" : value} onChange={(e) => onChange(e.target.valueAsNumber)} className="num pr-10" />
        {suffix && <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">{suffix}</span>}
      </div>
    </div>
  );
}

export function SwitchField({ id, label, checked, onChange }: { id: string; label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label htmlFor={id} className="flex cursor-pointer items-center justify-between rounded-lg border px-3 py-2 text-sm">
      {label}
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
    </label>
  );
}

export function ResultSkeleton() {
  return (
    <div className="space-y-4">
      <Card className="p-6"><Skeleton className="h-4 w-32" /><Skeleton className="mt-3 h-10 w-56" /><Skeleton className="mt-3 h-3 w-full" /></Card>
      <Skeleton className="h-[420px] w-full rounded-xl" />
    </div>
  );
}

export function ResultEmpty({ children }: { children: ReactNode }) {
  return <EmptyState icon={<MapPin className="size-6" />} title="Preencha o formulário para estimar">{children}</EmptyState>;
}

export function RangeBar({ min, max, value, fmt }: { min: number; max: number; value: number; fmt: (n: number) => string }) {
  const pos = ((value - min) / (max - min)) * 100;
  return (
    <div className="mt-5">
      <div className="relative h-2 rounded-full bg-primary-soft">
        <div className="absolute inset-y-0 left-[10%] right-[10%] rounded-full bg-primary/30" />
        <div className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card bg-primary" style={{ left: `${pos}%` }} />
      </div>
      <div className="num mt-2 flex justify-between text-xs text-muted-foreground">
        <span>mín. {fmt(min)}</span><span>faixa provável</span><span>máx. {fmt(max)}</span>
      </div>
    </div>
  );
}

export function LocationSection({ localizacao, pois }: { localizacao: Localizacao; pois: Poi[] }) {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
      <MapView
        className="h-[460px]"
        center={[localizacao.lat, localizacao.lon]}
        zoom={15}
        home={{ lat: localizacao.lat, lon: localizacao.lon, label: localizacao.endereco_formatado }}
        pois={pois}
      />
      <Card className="p-4">
        <h3 className="text-sm font-semibold">O que há por perto</h3>
        <p className="mb-2 text-xs text-muted-foreground">Mais próximo de cada categoria</p>
        <PoiList pois={pois} />
      </Card>
    </div>
  );
}

export function ModelFooter({ modelo }: { modelo: ModeloRef }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-4 text-xs text-muted-foreground">
      <span className="flex items-center gap-1.5"><Info className="size-3.5" /> Modelo <span className="font-mono text-foreground">{modelo.nome}</span> · versão <span className="font-mono text-foreground">{modelo.versao}</span></span>
      <Link to="/sobre" className="font-medium text-primary hover:underline">Como o modelo funciona</Link>
    </div>
  );
}

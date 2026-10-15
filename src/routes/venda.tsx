import { useMutation } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LocationSection, ModelFooter, NumField, RangeBar, ResultEmpty, ResultSkeleton, SwitchField } from "@/components/estimator";
import { ErrorState, PageHeader } from "@/components/states";
import { api, type CompraRequest, type TipoCompra } from "@/lib/api";
import { fmtBRL, fmtPct } from "@/lib/format";

const TIPOS: { v: TipoCompra; l: string }[] = [
  { v: "casa", l: "Casa" },
  { v: "apartamento", l: "Apartamento" },
  { v: "comercial", l: "Comercial" },
];

export const Route = createFileRoute("/venda")({
  head: () => ({
    meta: [
      { title: "Estimador de venda em Ponta Grossa (PR) — Preço Justo" },
      { name: "description", content: "Segundo modelo do projeto: preço de venda de imóveis em Ponta Grossa - PR." },
      { property: "og:title", content: "Estimador de venda em Ponta Grossa — Preço Justo" },
      { property: "og:description", content: "Preço de venda estimado por ML para Ponta Grossa - PR." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Venda,
});

function Venda() {
  const [f, setF] = useState<CompraRequest>({
    endereco: "Rua XV de Novembro, 500, Ponta Grossa - PR", area: 90, quartos: 3, banheiros: 2, vagas: 1, tipo: "casa", sobrado: false,
  });
  const [anunciado, setAnunciado] = useState("");
  const set = <K extends keyof CompraRequest>(k: K) => (v: CompraRequest[K]) => setF((s) => ({ ...s, [k]: v }));
  const m = useMutation({ mutationFn: api.preverCompra });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const a = Number(anunciado.replace(/\D/g, ""));
    m.mutate({ ...f, preco_anunciado: a > 0 ? a : undefined });
  };
  const enviado = m.variables;
  const r = m.data;
  return (
    <>
      <PageHeader eyebrow="Ponta Grossa - PR · modelo de venda" title="Estimador de preço de venda">
        Este é um segundo modelo, independente do de aluguel: foi treinado com anúncios de venda de outra cidade, Ponta Grossa, no Paraná.
      </PageHeader>
      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <Card className="h-fit p-5 lg:sticky lg:top-20">
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="endereco" className="text-xs text-muted-foreground">Endereço em Ponta Grossa</Label>
              <Input id="endereco" required value={f.endereco} onChange={(e) => set("endereco")(e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <NumField id="area" label="Área" suffix="m²" min={10} value={f.area} onChange={set("area")} />
              <NumField id="quartos" label="Quartos" value={f.quartos} onChange={set("quartos")} />
              <NumField id="banheiros" label="Banheiros" value={f.banheiros} onChange={set("banheiros")} />
              <NumField id="vagas" label="Vagas" value={f.vagas} onChange={set("vagas")} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Tipo</Label>
              <Select value={f.tipo ?? "casa"} onValueChange={(v) => set("tipo")(v as TipoCompra)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{TIPOS.map((t) => <SelectItem key={t.v} value={t.v}>{t.l}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <SwitchField id="sobrado" label="Sobrado" checked={!!f.sobrado} onChange={set("sobrado")} />
            <div className="space-y-1.5">
              <Label htmlFor="anunciado" className="text-xs text-muted-foreground">Preço anunciado (opcional)</Label>
              <Input id="anunciado" inputMode="numeric" className="num" placeholder="R$ 0" value={anunciado} onChange={(e) => setAnunciado(e.target.value)} />
            </div>
            <Button type="submit" className="w-full" disabled={m.isPending}>
              {m.isPending && <Loader2 className="size-4 animate-spin" />} Estimar preço
            </Button>
          </form>
        </Card>
        <div className="min-w-0">
          {m.isPending ? <ResultSkeleton /> : m.isError ? <ErrorState error={m.error} onRetry={() => enviado && m.mutate(enviado)} /> : r ? (
            <div className="space-y-4">
              <Card className="p-6">
                <div className="text-sm text-muted-foreground">Preço de venda estimado</div>
                <div className="num mt-1 text-4xl font-semibold tracking-tight sm:text-5xl">{fmtBRL(r.preco_estimado)}</div>
                <div className="num mt-1 text-sm text-muted-foreground">{fmtBRL(r.preco_estimado / (enviado?.area ?? f.area))}/m²</div>
                <RangeBar min={r.faixa.min} max={r.faixa.max} value={r.preco_estimado} fmt={fmtBRL} />
                {enviado?.preco_anunciado && (
                  <p className="mt-4 text-sm text-muted-foreground">
                    Anunciado por <span className="num font-medium text-foreground">{fmtBRL(enviado.preco_anunciado)}</span>:{" "}
                    <span className="num font-medium text-foreground">
                      {enviado.preco_anunciado > r.preco_estimado ? "+" : ""}{fmtPct((enviado.preco_anunciado / r.preco_estimado - 1) * 100)}
                    </span>{" "}em relação à estimativa.
                  </p>
                )}
              </Card>
              <p className="text-sm text-muted-foreground">{r.localizacao.endereco_formatado}</p>
              <LocationSection localizacao={r.localizacao} pois={r.pois_proximos} />
              <ModelFooter modelo={r.modelo} />
            </div>
          ) : <ResultEmpty>O preço estimado e o mapa do entorno aparecem aqui.</ResultEmpty>}
        </div>
      </div>
    </>
  );
}

import { useMutation } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Loader2, TrendingDown, TrendingUp, Minus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LocationSection, ModelFooter, NumField, RangeBar, ResultEmpty, ResultSkeleton, SwitchField } from "@/components/estimator";
import { ErrorState, PageHeader } from "@/components/states";
import { api, type AluguelRequest, type AluguelResponse, type TipoImovel } from "@/lib/api";
import { fmtBRL, fmtPct } from "@/lib/format";

export const Route = createFileRoute("/aluguel")({
  head: () => ({
    meta: [
      { title: "Estimador de aluguel em São Paulo — Preço Justo" },
      { name: "description", content: "Estime o aluguel justo de um imóvel em São Paulo e veja o custo total e o que há por perto." },
      { property: "og:title", content: "Estimador de aluguel em São Paulo — Preço Justo" },
      { property: "og:description", content: "Aluguel estimado por ML, faixa provável, custo total e pontos de interesse no mapa." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Aluguel,
});

const TIPOS: { v: TipoImovel; l: string }[] = [
  { v: "apartamento", l: "Apartamento" },
  { v: "studio", l: "Studio/Kitnet" },
  { v: "casa", l: "Casa" },
  { v: "casa_condominio", l: "Casa em condomínio" },
];

const inicial: AluguelRequest = {
  endereco: "Rua dos Pinheiros, 870", tipo: "apartamento", area: 65, quartos: 2, banheiros: 2, suites: 1, vagas: 1,
  mobiliado: false, ar_condicionado: false, piscina: false, academia: true, varanda: true,
};

function Aluguel() {
  const [f, setF] = useState<AluguelRequest>(inicial);
  const [anunciado, setAnunciado] = useState("");
  const set = <K extends keyof AluguelRequest>(k: K) => (v: AluguelRequest[K]) => setF((s) => ({ ...s, [k]: v }));
  const m = useMutation({ mutationFn: api.preverAluguel });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const a = Number(anunciado.replace(/\D/g, ""));
    m.mutate({ ...f, aluguel_anunciado: a > 0 ? a : undefined });
  };

  return (
    <>
      <PageHeader eyebrow="São Paulo · modelo de aluguel" title="Estimador de aluguel">
        Informe o imóvel e veja o aluguel que o modelo considera justo para a região.
      </PageHeader>
      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <Card className="h-fit p-5 lg:sticky lg:top-20">
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="endereco" className="text-xs text-muted-foreground">Endereço</Label>
              <Input id="endereco" required value={f.endereco} onChange={(e) => set("endereco")(e.target.value)} placeholder="Rua, número, bairro" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Tipo</Label>
              <Select value={f.tipo} onValueChange={(v) => set("tipo")(v as TipoImovel)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{TIPOS.map((t) => <SelectItem key={t.v} value={t.v}>{t.l}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <NumField id="area" label="Área" suffix="m²" min={10} value={f.area} onChange={set("area")} />
              <NumField id="quartos" label="Quartos" value={f.quartos} onChange={set("quartos")} />
              <NumField id="banheiros" label="Banheiros" value={f.banheiros} onChange={set("banheiros")} />
              <NumField id="suites" label="Suítes" value={f.suites} onChange={set("suites")} />
              <NumField id="vagas" label="Vagas" value={f.vagas} onChange={set("vagas")} />
            </div>
            <div className="grid gap-2">
              <SwitchField id="mobiliado" label="Mobiliado" checked={f.mobiliado} onChange={set("mobiliado")} />
              <SwitchField id="ar" label="Ar-condicionado" checked={f.ar_condicionado} onChange={set("ar_condicionado")} />
              <SwitchField id="piscina" label="Piscina" checked={f.piscina} onChange={set("piscina")} />
              <SwitchField id="academia" label="Academia" checked={f.academia} onChange={set("academia")} />
              <SwitchField id="varanda" label="Varanda" checked={f.varanda} onChange={set("varanda")} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="anunciado" className="text-xs text-muted-foreground">Aluguel anunciado (opcional)</Label>
              <Input id="anunciado" inputMode="numeric" className="num" placeholder="R$ 0" value={anunciado} onChange={(e) => setAnunciado(e.target.value)} />
            </div>
            <Button type="submit" className="w-full" disabled={m.isPending}>
              {m.isPending && <Loader2 className="size-4 animate-spin" />} Estimar aluguel
            </Button>
          </form>
        </Card>

        <div className="min-w-0">
          {m.isPending ? <ResultSkeleton /> : m.isError ? <ErrorState error={m.error} onRetry={() => m.variables && m.mutate(m.variables)} /> : m.data ? <Resultado r={m.data} /> : (
            <ResultEmpty>O resultado aparece aqui, com a faixa provável, o custo total e um mapa do entorno.</ResultEmpty>
          )}
        </div>
      </div>
    </>
  );
}

const SELO = {
  abaixo: { l: "Abaixo do mercado", c: "bg-success-soft text-success", i: TrendingDown },
  dentro: { l: "Dentro do mercado", c: "bg-primary-soft text-primary", i: Minus },
  acima: { l: "Acima do mercado", c: "bg-critical-soft text-critical", i: TrendingUp },
};

function Resultado({ r }: { r: AluguelResponse }) {
  const selo = r.comparacao && SELO[r.comparacao.classificacao];
  const temCusto = r.custo_total_estimado != null && r.custo_extra_pct != null;
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-[1.4fr_1fr]">
        <Card className="p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm text-muted-foreground">Aluguel estimado{r.bairro && ` · ${r.bairro}`}</div>
              <div className="num mt-1 text-4xl font-semibold tracking-tight sm:text-5xl">{fmtBRL(r.aluguel_estimado)}<span className="text-base font-normal text-muted-foreground">/mês</span></div>
            </div>
            {selo && r.comparacao && (
              <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${selo.c}`}>
                <selo.i className="size-3.5" /> {selo.l}
              </span>
            )}
          </div>
          <RangeBar min={r.faixa.min} max={r.faixa.max} value={r.aluguel_estimado} fmt={fmtBRL} />
          {r.comparacao && (
            <p className="mt-4 text-sm text-muted-foreground">
              Anunciado por <span className="num font-medium text-foreground">{fmtBRL(r.comparacao.aluguel_anunciado)}</span>:{" "}
              <span className="num font-medium text-foreground">{r.comparacao.diferenca_pct > 0 ? "+" : ""}{fmtPct(r.comparacao.diferenca_pct)}</span> em relação à estimativa.
            </p>
          )}
        </Card>
        <Card className="p-6">
          <div className="text-sm text-muted-foreground">Custo total estimado</div>
          {temCusto ? (
            <>
              <div className="num mt-1 text-3xl font-semibold">{fmtBRL(r.custo_total_estimado!)}</div>
              <dl className="num mt-4 space-y-2 text-sm">
                <div className="flex justify-between"><dt className="text-muted-foreground">Aluguel</dt><dd>{fmtBRL(r.aluguel_estimado)}</dd></div>
                <div className="flex justify-between"><dt className="text-muted-foreground">Condomínio + IPTU ({fmtPct(r.custo_extra_pct!)})</dt><dd>{fmtBRL(r.custo_total_estimado! - r.aluguel_estimado)}</dd></div>
              </dl>
              <p className="mt-3 text-xs text-muted-foreground">Percentual mediano observado no bairro.</p>
            </>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">Sem dados de condomínio e IPTU para este bairro.</p>
          )}
        </Card>
      </div>
      <p className="text-sm text-muted-foreground">{r.localizacao.endereco_formatado}</p>
      <LocationSection localizacao={r.localizacao} pois={r.pois_proximos} />
      <ModelFooter modelo={r.modelo} />
    </div>
  );
}

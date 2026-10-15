import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, Brain, MapPin, Receipt, Route as RouteIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/states";
import { api, qk } from "@/lib/api";
import { fmtData, fmtNum, fmtPct } from "@/lib/format";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Preço Justo — Quanto vale o aluguel em São Paulo?" },
      { name: "description", content: "Estimativa de aluguel em São Paulo por um modelo de Machine Learning treinado com ~22 mil anúncios reais." },
      { property: "og:title", content: "Preço Justo — Quanto vale o aluguel em São Paulo?" },
      { property: "og:description", content: "Estimativa de aluguel por Machine Learning, com mapa, pontos de interesse e custo total." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Inicio,
});

const passos = [
  { icon: MapPin, t: "Endereço", d: "Você informa o endereço e as características do imóvel." },
  { icon: RouteIcon, t: "Localização e entorno", d: "Geocodificamos e medimos a distância até metrô, escolas, hospitais, parques e mais." },
  { icon: Brain, t: "Modelo", d: "Um modelo de gradient boosting combina tudo isso com o histórico do bairro." },
  { icon: Receipt, t: "Preço e custo total", d: "Você recebe o aluguel estimado, a faixa provável e o custo com condomínio e IPTU." },
];

function Inicio() {
  const q = useQuery({ queryKey: qk.modelos, queryFn: api.modelos });
  const m = q.data?.modelos.find((x) => x.chave === "aluguel");
  return (
    <div className="space-y-20">
      <section className="max-w-3xl pt-6">
        <p className="mb-4 text-xs font-semibold uppercase tracking-wider text-primary">Inteligência de preços · São Paulo</p>
        <h1 className="text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl">Quanto vale o aluguel desse imóvel em São Paulo?</h1>
        <p className="mt-5 max-w-2xl text-lg text-muted-foreground">
          O preço é estimado por um modelo de Machine Learning treinado com cerca de 22 mil anúncios reais, considerando o imóvel, o bairro e o que existe ao redor dele.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button asChild size="lg"><Link to="/aluguel">Estimar aluguel <ArrowRight className="size-4" /></Link></Button>
          <Button asChild size="lg" variant="outline"><Link to="/modelo">Ver o modelo em produção</Link></Button>
        </div>
      </section>

      <section>
        {q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : (
          <Card className="grid grid-cols-2 divide-border p-0 sm:grid-cols-4 sm:divide-x">
            {[
              ["Anúncios analisados", m && fmtNum(m.n_treino)],
              ["R² do modelo", m && m.metricas.r2.toLocaleString("pt-BR", { minimumFractionDigits: 3 })],
              ["Erro médio (MAPE)", m && fmtPct(m.metricas.mape)],
              ["Última atualização", m && fmtData(m.treinado_em)],
            ].map(([l, v]) => (
              <div key={l} className="p-6">
                <div className="text-xs text-muted-foreground">{l}</div>
                {v ? <div className="num mt-2 text-2xl font-semibold sm:text-3xl">{v}</div> : <Skeleton className="mt-2 h-8 w-24" />}
              </div>
            ))}
          </Card>
        )}
      </section>

      <section>
        <h2 className="text-xl font-semibold tracking-tight">Como funciona</h2>
        <ol className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {passos.map((p, i) => (
            <li key={p.t}>
              <Card className="h-full p-5">
                <div className="flex items-center justify-between">
                  <span className="flex size-9 items-center justify-center rounded-lg bg-primary-soft text-primary"><p.icon className="size-4" /></span>
                  <span className="num text-xs text-muted-foreground">0{i + 1}</span>
                </div>
                <h3 className="mt-4 font-medium">{p.t}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{p.d}</p>
              </Card>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

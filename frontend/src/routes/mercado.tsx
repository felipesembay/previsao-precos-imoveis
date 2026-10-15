import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { MapView } from "@/components/map/MapView";
import { ErrorState, PageHeader } from "@/components/states";
import { useTheme } from "@/components/theme";
import { api, qk, type Regiao } from "@/lib/api";
import { fmtBRL, fmtNum } from "@/lib/format";

export const Route = createFileRoute("/mercado")({
  head: () => ({
    meta: [
      { title: "Mercado de aluguel em São Paulo — Preço Justo" },
      {
        name: "description",
        content:
          "R$/m² mediano por região de São Paulo e os principais achados da análise de ~22 mil anúncios.",
      },
      { property: "og:title", content: "Mercado de aluguel em São Paulo — Preço Justo" },
      {
        property: "og:description",
        content: "Onde o aluguel é mais caro em São Paulo e o que realmente pesa no preço.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Mercado,
});

const NIVEIS = ["--seq-1", "--seq-2", "--seq-3", "--seq-4", "--seq-5"] as const;

/** Lê as cores da escala sequencial do tema atual (o Leaflet desenha em SVG e não resolve var()). */
function useCoresSequenciais() {
  const { theme } = useTheme();
  const [cores, setCores] = useState<string[]>([]);
  useEffect(() => {
    const css = getComputedStyle(document.documentElement);
    setCores(NIVEIS.map((n) => css.getPropertyValue(n).trim()));
  }, [theme]);
  return cores;
}

/** Limites dos 5 níveis por quintis do R$/m² (cada cor tem o mesmo número de regiões). */
function quintis(valores: number[]) {
  const v = [...valores].sort((a, b) => a - b);
  return [0.2, 0.4, 0.6, 0.8].map((q) => v[Math.floor(q * (v.length - 1))]!);
}
const nivel = (x: number, cortes: number[]) => cortes.filter((c) => x > c).length;

function Mercado() {
  const q = useQuery({ queryKey: qk.regioes, queryFn: api.regioes });
  const regioes = q.data?.regioes ?? [];
  return (
    <>
      <PageHeader eyebrow="São Paulo · análise de mercado" title="Mercado de aluguel">
        R$/m² mediano das regiões com pelo menos 30 anúncios, a partir de ~22 mil anúncios do
        QuintoAndar.
      </PageHeader>
      <div className="space-y-10">
        {q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : !q.data ? (
          <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
            <Skeleton className="h-[520px] rounded-xl" />
            <Skeleton className="h-[520px] rounded-xl" />
          </div>
        ) : (
          <MapaERanking regioes={regioes} />
        )}
        <Achados />
      </div>
    </>
  );
}

function MapaERanking({ regioes }: { regioes: Regiao[] }) {
  const cores = useCoresSequenciais();
  const cortes = useMemo(() => quintis(regioes.map((r) => r.aluguel_m2_mediano)), [regioes]);
  const maxN = Math.max(...regioes.map((r) => r.n_anuncios));
  const circulos = cores.length
    ? regioes.map((r) => ({
        lat: r.lat,
        lon: r.lon,
        radius: 5 + 13 * Math.sqrt(r.n_anuncios / maxN),
        color: cores[nivel(r.aluguel_m2_mediano, cortes)]!,
        label: `${r.nome}: ${fmtBRL(r.aluguel_m2_mediano)}/m² · aluguel mediano ${fmtBRL(r.aluguel_mediano)} · ${fmtNum(r.n_anuncios)} anúncios`,
      }))
    : [];
  const minimo = Math.min(...regioes.map((r) => r.aluguel_m2_mediano));
  const maximo = Math.max(...regioes.map((r) => r.aluguel_m2_mediano));
  const faixas = [minimo, ...cortes, maximo];

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
      <div>
        <MapView className="h-[520px]" center={[-23.58, -46.64]} zoom={11} circles={circulos} />
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">R$/m² mediano</span>
          {cores.map((c, i) => (
            <span key={c + i} className="num flex items-center gap-1.5">
              <span className="size-3 rounded-full" style={{ background: c }} />
              {fmtNum(Math.round(faixas[i]!))}–{fmtNum(Math.round(faixas[i + 1]!))}
            </span>
          ))}
          <span>· tamanho do círculo = número de anúncios</span>
        </div>
      </div>
      <Ranking regioes={regioes} />
    </div>
  );
}

function Ranking({ regioes }: { regioes: Regiao[] }) {
  const ordenadas = [...regioes].sort((a, b) => b.aluguel_m2_mediano - a.aluguel_m2_mediano);
  const max = ordenadas[0]?.aluguel_m2_mediano ?? 1;
  const Lista = ({ itens }: { itens: Regiao[] }) => (
    <ul className="space-y-1.5">
      {itens.map((r) => (
        <li
          key={r.nome}
          className="grid grid-cols-[120px_1fr_64px] items-center gap-2 text-xs"
          title={`${r.nome}: ${fmtBRL(r.aluguel_m2_mediano)}/m² · ${fmtNum(r.n_anuncios)} anúncios`}
        >
          <span className="truncate">{r.nome}</span>
          <div className="h-2 rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${(r.aluguel_m2_mediano / max) * 100}%` }}
            />
          </div>
          <span className="num text-right">{fmtBRL(r.aluguel_m2_mediano)}</span>
        </li>
      ))}
    </ul>
  );
  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold">Mais caras</h3>
      <p className="mb-3 text-xs text-muted-foreground">R$/m² mediano</p>
      <Lista itens={ordenadas.slice(0, 8)} />
      <h3 className="mt-6 text-sm font-semibold">Mais baratas</h3>
      <p className="mb-3 text-xs text-muted-foreground">R$/m² mediano</p>
      <Lista itens={ordenadas.slice(-8).reverse()} />
      <p className="mt-4 text-xs text-muted-foreground">
        {fmtNum(regioes.length)} regiões com pelo menos 30 anúncios.
      </p>
    </Card>
  );
}

function Achados() {
  const q = useQuery({ queryKey: qk.achados, queryFn: api.achados });
  return (
    <section>
      <h2 className="text-lg font-semibold tracking-tight">O que pesa no preço</h2>
      <p className="mb-4 mt-1 text-sm text-muted-foreground">
        Efeitos estimados com regressão controlando tamanho e região: comparam imóveis parecidos,
        não médias brutas.
      </p>
      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {q.data
            ? q.data.achados.map((a) => (
                <Card key={a.titulo} className="p-5">
                  <div className="num text-2xl font-semibold text-primary">{a.valor}</div>
                  <h3 className="mt-2 font-medium">{a.titulo}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{a.descricao}</p>
                </Card>
              ))
            : [0, 1, 2].map((i) => <Skeleton key={i} className="h-36 rounded-xl" />)}
        </div>
      )}
    </section>
  );
}

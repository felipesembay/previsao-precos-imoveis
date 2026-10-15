import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  Database,
  Gauge,
  Server,
  Upload,
  XCircle,
} from "lucide-react";
import type { ReactNode } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState, Metric, PageHeader } from "@/components/states";
import { api, qk, type Modelo, type MonitoramentoResponse, type Retreino } from "@/lib/api";
import { fmtBytes, fmtData, fmtNum, fmtPct } from "@/lib/format";
import { rotuloFeature } from "@/lib/rotulos";

export const Route = createFileRoute("/modelo")({
  head: () => ({
    meta: [
      { title: "Modelo em produção — Preço Justo" },
      {
        name: "description",
        content:
          "Modelo em produção, erro real ao longo do tempo, drift das features e histórico de retreinos.",
      },
      { property: "og:title", content: "Modelo em produção — Preço Justo" },
      {
        property: "og:description",
        content:
          "MLOps na prática: monitoramento, drift e retreino automático champion × challenger.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: ModeloPage,
});

const MIN_AMOSTRAS = 30; // abaixo disso o drift é só indicativo (mesmo critério dos alertas)

function ModeloPage() {
  return (
    <>
      <PageHeader eyebrow="MLOps" title="Modelo em produção">
        O modelo de aluguel é monitorado de hora em hora e retreinado automaticamente quando o erro
        real ou o drift passam do limite. Um modelo novo só entra em produção se errar menos que o
        atual.
      </PageHeader>
      <div className="space-y-10">
        <Modelos />
        <Monitoramento />
        <Retreinos />
        <Infra />
      </div>
    </>
  );
}

function Secao({
  titulo,
  descricao,
  children,
}: {
  titulo: string;
  descricao?: string;
  children: ReactNode;
}) {
  return (
    <section>
      <h2 className="text-lg font-semibold tracking-tight">{titulo}</h2>
      {descricao && <p className="mb-4 mt-1 text-sm text-muted-foreground">{descricao}</p>}
      {!descricao && <div className="mb-4" />}
      {children}
    </section>
  );
}

// ── Modelos ──────────────────────────────────────────────────────────────────
function Modelos() {
  const q = useQuery({ queryKey: qk.modelos, queryFn: api.modelos });
  return (
    <Secao
      titulo="Modelos"
      descricao="Versão em produção (@champion no MLflow Model Registry) e métricas no conjunto de teste."
    >
      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {q.data
            ? q.data.modelos.map((m) => <CardModelo key={m.chave} m={m} />)
            : [0, 1].map((i) => <Skeleton key={i} className="h-44 rounded-xl" />)}
        </div>
      )}
    </Secao>
  );
}

function CardModelo({ m }: { m: Modelo }) {
  const titulo = m.chave === "aluguel" ? "Aluguel · São Paulo" : "Venda · Ponta Grossa";
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs text-muted-foreground">{titulo}</div>
          <div className="mt-1 font-mono text-sm">{m.nome}</div>
        </div>
        <span className="rounded-full bg-primary-soft px-2.5 py-1 font-mono text-xs font-medium text-primary">
          {/* Só o aluguel tem retreino automático e alias @champion no Model Registry */}
          {m.chave === "aluguel" ? "@champion" : "em produção"} {m.versao}
        </span>
      </div>
      <div className="mt-5 grid grid-cols-3 gap-4">
        <Metric
          label="R²"
          value={m.metricas.r2.toLocaleString("pt-BR", {
            minimumFractionDigits: 3,
            maximumFractionDigits: 3,
          })}
        />
        <Metric
          label="MAE"
          value={
            m.metricas.mae_reais != null ? `R$ ${fmtNum(Math.round(m.metricas.mae_reais))}` : "—"
          }
        />
        <Metric label="MAPE" value={m.metricas.mape != null ? fmtPct(m.metricas.mape) : "—"} />
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        Treinado em {fmtData(m.treinado_em)}
        {m.n_treino != null && ` · ${fmtNum(m.n_treino)} anúncios no treino`}
        {m.metricas.mape == null && " · métricas em R$ não registradas no treino deste modelo"}
      </p>
    </Card>
  );
}

// ── Monitoramento ────────────────────────────────────────────────────────────
function Monitoramento() {
  const q = useQuery({ queryKey: qk.monitoramento, queryFn: api.monitoramento });
  return (
    <Secao
      titulo="Monitoramento do aluguel"
      descricao="Janela dos últimos 14 dias de previsões feitas pelo site e pelas telas."
    >
      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !q.data ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-72 rounded-xl" />
          <Skeleton className="h-72 rounded-xl" />
        </div>
      ) : (
        <div className="space-y-4">
          <Alertas alertas={q.data.alertas} />
          <div className="grid gap-4 lg:grid-cols-2">
            <GraficoMape d={q.data} />
            <Drift d={q.data} />
          </div>
        </div>
      )}
    </Secao>
  );
}

function Alertas({ alertas }: { alertas: MonitoramentoResponse["alertas"] }) {
  if (!alertas.length) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-success/30 bg-success-soft px-4 py-3 text-sm">
        <CheckCircle2 className="size-4 text-success" /> Nenhum alerta ativo.
      </div>
    );
  }
  return (
    <ul className="space-y-2">
      {alertas.map((a) => {
        const critico = a.severidade === "critical";
        return (
          <li
            key={a.nome + a.desde}
            className={`flex items-start gap-3 rounded-xl border px-4 py-3 text-sm ${critico ? "border-critical/30 bg-critical-soft" : "border-warning/30 bg-warning-soft"}`}
          >
            {critico ? (
              <XCircle className="mt-0.5 size-4 shrink-0 text-critical" />
            ) : (
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />
            )}
            <div className="min-w-0">
              <div className="font-medium">{a.resumo || a.nome}</div>
              <div className="text-xs text-muted-foreground">
                {critico ? "Crítico" : "Atenção"} · {a.nome} · desde{" "}
                {new Date(a.desde).toLocaleString("pt-BR", {
                  dateStyle: "short",
                  timeStyle: "short",
                })}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

const dataCurta = (iso: string) =>
  new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
const horaCurta = (iso: string) =>
  new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
const DIA_MS = 864e5;
const dataHora = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });

function GraficoMape({ d }: { d: MonitoramentoResponse }) {
  const ultimo = d.mape_serie.at(-1);
  const acima = ultimo != null && ultimo.mape > d.mape_limite;
  // Eixo de tempo real (medições irregulares não ficam igualmente espaçadas)
  const pontos = d.mape_serie.map((p) => ({ t: Date.parse(p.data), mape: p.mape }));
  // Série curta (menos de 2 dias): o eixo mostra a hora, senão repetiria o mesmo dia
  const primeiro = d.mape_serie[0];
  const curta =
    primeiro != null &&
    ultimo != null &&
    Date.parse(ultimo.data) - Date.parse(primeiro.data) < 2 * DIA_MS;
  return (
    <Card className="p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold">Erro real (MAPE) ao longo do tempo</h3>
        {ultimo && (
          <span
            className={`num text-sm font-medium ${acima ? "text-critical" : "text-foreground"}`}
          >
            última medição {fmtPct(ultimo.mape)} · {dataHora(ultimo.data)}
          </span>
        )}
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Previsões em que o valor do anúncio foi informado · limite {fmtPct(d.mape_limite)}
      </p>
      {d.mape_serie.length === 0 ? (
        <EmptyState icon={<Gauge className="size-6" />} title="Sem erro medido na janela">
          O MAPE aparece quando houver previsões com o aluguel anunciado.
        </EmptyState>
      ) : (
        <div className="h-60">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={pontos} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis
                dataKey="t"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickFormatter={(t: number) =>
                  (curta ? horaCurta : dataCurta)(new Date(t).toISOString())
                }
                tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                tickLine={false}
                axisLine={false}
                minTickGap={24}
              />
              <YAxis
                tickFormatter={(v: number) => `${Math.round(v)}%`}
                tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                tickLine={false}
                axisLine={false}
                domain={[0, (max: number) => Math.ceil(Math.max(max, d.mape_limite) * 1.15)]}
              />
              <ReferenceLine
                y={d.mape_limite}
                stroke="var(--critical)"
                strokeDasharray="4 4"
                label={{
                  value: `limite ${fmtPct(d.mape_limite)}`,
                  position: "insideTopRight",
                  fontSize: 11,
                  fill: "var(--muted-foreground)",
                }}
              />
              <Tooltip
                cursor={{ stroke: "var(--muted-foreground)", strokeDasharray: "3 3" }}
                contentStyle={{
                  background: "var(--popover)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelFormatter={(t) => dataHora(new Date(Number(t)).toISOString())}
                formatter={(v) => [fmtPct(Number(v)), "MAPE"]}
              />
              <Line
                type="linear"
                dataKey="mape"
                stroke="var(--chart-1)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--card)" }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

const STATUS = {
  ok: { l: "OK", cor: "var(--success)", texto: "text-success", i: CheckCircle2 },
  atencao: { l: "Atenção", cor: "var(--warning)", texto: "text-warning", i: CircleAlert },
  critico: { l: "Crítico", cor: "var(--critical)", texto: "text-critical", i: XCircle },
} as const;

const INDICATIVO = {
  l: "Indicativo",
  cor: "var(--muted-foreground)",
  texto: "text-muted-foreground",
  i: CircleAlert,
} as const;

function Drift({ d }: { d: MonitoramentoResponse }) {
  const pouco = d.n_amostras < MIN_AMOSTRAS;
  const escala = Math.max(0.5, ...d.drift.map((f) => f.score));
  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold">Drift das features</h3>
      <p className="mb-3 text-xs text-muted-foreground">
        Distância de Wasserstein entre produção e treino ({fmtNum(d.n_amostras)} amostras) · atenção
        ≥ 0,10 · crítico ≥ 0,30
        {pouco && d.drift.length > 0 && (
          <span className="text-warning">
            {" "}
            · menos de {MIN_AMOSTRAS} amostras: valores indicativos, sem status nem alertas
          </span>
        )}
      </p>
      {d.drift.length === 0 ? (
        <EmptyState title="Sem previsões nos últimos 14 dias">
          O drift é calculado quando o modelo recebe uso.
        </EmptyState>
      ) : (
        <ul className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
          {d.drift.map((f) => {
            // Com amostra pequena qualquer diferença parece drift: mostra o valor, sem cor de status
            const s = pouco ? INDICATIVO : STATUS[f.status];
            return (
              <li
                key={f.feature}
                className="grid grid-cols-[150px_1fr_76px] items-center gap-3 text-xs"
                title={`${rotuloFeature(f.feature)}: ${f.score.toFixed(3)}`}
              >
                <span className="truncate">{rotuloFeature(f.feature)}</span>
                <div className="relative h-2 rounded-full bg-muted">
                  <div
                    className="absolute inset-y-0 left-0 rounded-full"
                    style={{
                      width: `${Math.max(2, (Math.min(f.score, escala) / escala) * 100)}%`,
                      background: s.cor,
                    }}
                  />
                  <div
                    className="absolute inset-y-[-3px] w-px bg-muted-foreground/40"
                    style={{ left: `${(0.1 / escala) * 100}%` }}
                  />
                  <div
                    className="absolute inset-y-[-3px] w-px bg-muted-foreground/40"
                    style={{ left: `${(0.3 / escala) * 100}%` }}
                  />
                </div>
                <span className={`num flex items-center justify-end gap-1 ${s.texto}`}>
                  <s.i className="size-3" />
                  {f.score.toLocaleString("pt-BR", {
                    maximumFractionDigits: 2,
                    minimumFractionDigits: 2,
                  })}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

// ── Retreinos ────────────────────────────────────────────────────────────────
function Retreinos() {
  const q = useQuery({ queryKey: qk.retreinos, queryFn: api.retreinos });
  return (
    <Secao
      titulo="Retreinos automáticos"
      descricao="Cada linha é um desafiante treinado pelo Airflow e comparado com o modelo em produção no mesmo conjunto de teste."
    >
      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !q.data ? (
        <Skeleton className="h-40 rounded-xl" />
      ) : q.data.retreinos.length === 0 ? (
        <EmptyState title="Nenhum retreino ainda" />
      ) : (
        <ol className="relative space-y-3 border-l pl-6">
          {q.data.retreinos.map((r) => (
            <ItemRetreino key={r.data} r={r} />
          ))}
        </ol>
      )}
    </Secao>
  );
}

function ItemRetreino({ r }: { r: Retreino }) {
  return (
    <li className="relative">
      <span
        className={`absolute -left-[31px] top-4 size-2.5 rounded-full ring-4 ring-background ${r.promovido ? "bg-success" : "bg-muted-foreground"}`}
      />
      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm">
            <span className="font-mono font-medium">{r.versao_challenger}</span>
            <span className="text-muted-foreground"> desafiou </span>
            <span className="font-mono">{r.versao_champion ?? "—"}</span>
            <span className="text-muted-foreground"> · {dataHora(r.data)}</span>
          </div>
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${r.promovido ? "bg-success-soft text-success" : "bg-muted text-muted-foreground"}`}
          >
            {r.promovido ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}
            {r.promovido ? "Promovido" : "Rejeitado"}
          </span>
        </div>
        <div className="num mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <span>
            MAPE desafiante <strong>{fmtPct(r.mape_challenger)}</strong>
          </span>
          {r.mape_champion != null && (
            <span>
              MAPE em produção <strong>{fmtPct(r.mape_champion)}</strong>
            </span>
          )}
        </div>
        {r.motivo && <p className="mt-1 text-xs text-muted-foreground">Gatilho: {r.motivo}</p>}
      </Card>
    </li>
  );
}

// ── Infraestrutura ───────────────────────────────────────────────────────────
function Infra() {
  const q = useQuery({ queryKey: qk.infra, queryFn: api.infra });
  const d = q.data;
  return (
    <Secao
      titulo="Infraestrutura"
      descricao="Banco de dados PostgreSQL no Azure, dentro do plano gratuito (750 h/mês e 32 GB)."
    >
      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !d ? (
        <Skeleton className="h-28 rounded-xl" />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {d.horas_mes != null && (
            <CardUso
              icon={<Server className="size-4" />}
              titulo="Horas do servidor no mês"
              valor={`${fmtNum(Math.round(d.horas_mes))} h`}
              detalhe={`de ${fmtNum(d.horas_limite)} h gratuitas`}
              frac={d.horas_mes / d.horas_limite}
            />
          )}
          <CardUso
            icon={<Database className="size-4" />}
            titulo="Banco de dados"
            valor={fmtBytes(d.banco_bytes)}
            detalhe={`de ${fmtBytes(d.banco_limite_bytes)} gratuitos`}
            frac={d.banco_bytes / d.banco_limite_bytes}
          />
          <CardUso
            icon={<Upload className="size-4" />}
            titulo="Inserções em 24 h"
            valor={fmtNum(d.insercoes_24h)}
            detalhe="linhas gravadas no banco"
          />
          <CardUso
            icon={<Gauge className="size-4" />}
            titulo="Previsões registradas"
            valor={fmtNum(d.previsoes_total)}
            detalhe="aluguel + venda, desde o início"
          />
        </div>
      )}
    </Secao>
  );
}

function CardUso({
  icon,
  titulo,
  valor,
  detalhe,
  frac,
}: {
  icon: ReactNode;
  titulo: string;
  valor: string;
  detalhe: string;
  frac?: number;
}) {
  const cor =
    frac == null ? "" : frac >= 1 ? "bg-critical" : frac >= 0.9 ? "bg-warning" : "bg-primary";
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {icon}
        {titulo}
      </div>
      <div className="num mt-2 text-2xl font-semibold">{valor}</div>
      <div className="text-xs text-muted-foreground">{detalhe}</div>
      {frac != null && (
        <div className="mt-3 h-1.5 rounded-full bg-muted" title={fmtPct(frac * 100)}>
          <div
            className={`h-full rounded-full ${cor}`}
            style={{ width: `${Math.max(1, Math.min(100, frac * 100))}%` }}
          />
        </div>
      )}
    </Card>
  );
}

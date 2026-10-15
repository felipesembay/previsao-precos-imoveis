import { createFileRoute } from "@tanstack/react-router";
import {
  ArrowRight,
  Brain,
  Database,
  Github,
  LineChart,
  MapPinned,
  RefreshCcw,
  Server,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/states";

export const Route = createFileRoute("/sobre")({
  head: () => ({
    meta: [
      { title: "Sobre o projeto — Preço Justo" },
      {
        name: "description",
        content:
          "Como a plataforma funciona: coleta, features geoespaciais, treino, MLflow, API, monitoramento e retreino automático.",
      },
      { property: "og:title", content: "Sobre o projeto — Preço Justo" },
      {
        property: "og:description",
        content: "Projeto de portfólio de Ciência de Dados e Engenharia de Machine Learning.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Sobre,
});

const REPOSITORIO = "https://github.com/felipesembay/previsao-precos-imoveis";

const ETAPAS = [
  {
    icon: Database,
    t: "Coleta",
    d: "~30 mil anúncios da API do QuintoAndar, varrendo São Paulo em 169 quadrantes.",
  },
  {
    icon: MapPinned,
    t: "Features geoespaciais",
    d: "Distâncias e contagens de 12 categorias de pontos de interesse do OpenStreetMap.",
  },
  {
    icon: Brain,
    t: "Treino",
    d: "XGBoost com 250 trials de Optuna, comparado a uma regressão linear de referência.",
  },
  {
    icon: Server,
    t: "MLflow + API",
    d: "A versão em produção recebe o alias @champion; a API FastAPI serve as previsões.",
  },
  {
    icon: LineChart,
    t: "Monitoramento",
    d: "Drift das features (Evidently) e erro real de hora em hora, com alertas por e-mail.",
  },
  {
    icon: RefreshCcw,
    t: "Retreino automático",
    d: "O Airflow retreina quando o erro ou o drift passam do limite; só promove se errar menos.",
  },
];

const STACK = [
  "Python",
  "pandas",
  "GeoPandas",
  "XGBoost",
  "Optuna",
  "scikit-learn",
  "MLflow",
  "FastAPI",
  "Evidently",
  "Airflow",
  "PostgreSQL (Azure)",
  "Terraform",
  "Prometheus",
  "Grafana",
  "Alertmanager",
  "Docker",
  "React",
  "TanStack",
];

const DECISOES = [
  {
    t: "Localização só pelo endereço",
    d: "O modelo não usa o nome do bairro: o endereço vira lat/lon e, daí, distâncias ao centro, a polos de emprego e a pontos de interesse.",
  },
  {
    t: "Comparação justa no retreino",
    d: "O desafiante e o modelo atual são avaliados só em anúncios que nenhum dos dois viu no treino; sem isso, o modelo antigo levava vantagem.",
  },
  {
    t: "Treino e produção iguais",
    d: "O mesmo código calcula as features no treino e na API, e as tarefas do Airflow rodam na mesma imagem Docker das telas.",
  },
  {
    t: "Custo zero na nuvem",
    d: "O banco roda no plano gratuito do Azure; o Terraform fixa só opções gratuitas e um orçamento avisa por e-mail qualquer gasto.",
  },
];

function Sobre() {
  return (
    <>
      <PageHeader eyebrow="Projeto de portfólio" title="Sobre o projeto">
        Uma plataforma de ponta a ponta de Ciência de Dados e Engenharia de Machine Learning: da
        coleta dos dados ao modelo em produção que se monitora e se retreina sozinho.
      </PageHeader>

      <div className="space-y-12">
        <section>
          <h2 className="text-lg font-semibold tracking-tight">Como funciona</h2>
          <p className="mb-5 mt-1 text-sm text-muted-foreground">
            O ciclo fecha no retreino: quando o modelo degrada, o fluxo volta à coleta com dados
            novos.
          </p>
          <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {ETAPAS.map((e, i) => (
              <li key={e.t}>
                <Card className="relative h-full p-5">
                  <div className="flex items-center justify-between">
                    <span className="flex size-9 items-center justify-center rounded-lg bg-primary-soft text-primary">
                      <e.icon className="size-4" />
                    </span>
                    <span className="num text-xs text-muted-foreground">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                  </div>
                  <h3 className="mt-4 flex items-center gap-1.5 font-medium">
                    {e.t}
                    {i < ETAPAS.length - 1 && (
                      <ArrowRight className="size-3.5 text-muted-foreground" />
                    )}
                    {i === ETAPAS.length - 1 && (
                      <RefreshCcw className="size-3.5 text-muted-foreground" />
                    )}
                  </h3>
                  <p className="mt-1 text-sm text-muted-foreground">{e.d}</p>
                </Card>
              </li>
            ))}
          </ol>
        </section>

        <section>
          <h2 className="text-lg font-semibold tracking-tight">Decisões que importam</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {DECISOES.map((d) => (
              <Card key={d.t} className="flex gap-3 p-5">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" />
                <div>
                  <h3 className="font-medium">{d.t}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{d.d}</p>
                </div>
              </Card>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-lg font-semibold tracking-tight">Stack</h2>
          <ul className="mt-4 flex flex-wrap gap-2">
            {STACK.map((s) => (
              <li key={s} className="rounded-full border bg-card px-3 py-1 text-sm">
                {s}
              </li>
            ))}
          </ul>
        </section>

        <section className="flex flex-wrap gap-3">
          <Button asChild variant="outline">
            <a href={REPOSITORIO} target="_blank" rel="noreferrer">
              <Github className="size-4" /> Código no GitHub
            </a>
          </Button>
        </section>
      </div>
    </>
  );
}

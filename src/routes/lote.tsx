import { useMutation } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { ArrowDownUp, Download, FileSpreadsheet, Loader2, Upload } from "lucide-react";
import { useMemo, useRef, useState, type DragEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState, ErrorState, Metric, PageHeader } from "@/components/states";
import { api, type LinhaLote } from "@/lib/api";
import { fmtBRL, fmtNum } from "@/lib/format";

export const Route = createFileRoute("/lote")({
  head: () => ({
    meta: [
      { title: "Avaliação em lote — Preço Justo" },
      {
        name: "description",
        content: "Estime o aluguel de vários imóveis de uma vez a partir de um arquivo CSV.",
      },
      { property: "og:title", content: "Avaliação em lote — Preço Justo" },
      {
        property: "og:description",
        content: "Envie um CSV e receba o aluguel estimado de cada imóvel.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Lote,
});

const MAX_LINHAS = 200;
const COLUNAS = [
  "endereco",
  "tipo",
  "area",
  "quartos",
  "banheiros",
  "suites",
  "vagas",
  "mobiliado",
  "ar_condicionado",
  "piscina",
  "academia",
  "varanda",
  "aluguel_anunciado",
] as const;
const EXEMPLO = [
  [
    "Av. Paulista, 1000, São Paulo - SP",
    "apartamento",
    "80",
    "2",
    "2",
    "1",
    "1",
    "false",
    "true",
    "false",
    "true",
    "true",
    "5500",
  ],
  [
    "Rua Vergueiro, 3000, São Paulo - SP",
    "studio",
    "30",
    "0",
    "1",
    "0",
    "0",
    "true",
    "true",
    "false",
    "false",
    "false",
    "",
  ],
  [
    "Rua Tuiuti, 2000, São Paulo - SP",
    "casa",
    "120",
    "3",
    "2",
    "1",
    "2",
    "false",
    "false",
    "false",
    "false",
    "true",
    "4000",
  ],
];

const csvCelula = (v: unknown) => {
  const s = v == null ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};
function baixar(nome: string, linhas: unknown[][]) {
  const blob = new Blob(["﻿" + linhas.map((l) => l.map(csvCelula).join(",")).join("\n")], {
    type: "text/csv;charset=utf-8",
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = nome;
  a.click();
  URL.revokeObjectURL(a.href);
}

type Ordem = { col: "endereco" | "area" | "aluguel_estimado"; desc: boolean };

function Lote() {
  const input = useRef<HTMLInputElement>(null);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [arrastando, setArrastando] = useState(false);
  const [ordem, setOrdem] = useState<Ordem>({ col: "aluguel_estimado", desc: true });
  const m = useMutation({ mutationFn: api.preverLote });

  const escolher = (f: File | undefined) => {
    if (!f) return;
    setArquivo(f);
    m.mutate(f);
  };
  const soltar = (e: DragEvent) => {
    e.preventDefault();
    setArrastando(false);
    escolher(e.dataTransfer.files[0]);
  };

  const linhas = useMemo(() => {
    const ls = [...(m.data?.linhas ?? [])];
    const val = (l: LinhaLote) => l[ordem.col] ?? (ordem.col === "endereco" ? "" : -Infinity);
    ls.sort((a, b) => {
      const x = val(a),
        y = val(b);
      const c = typeof x === "string" ? x.localeCompare(String(y)) : (x as number) - (y as number);
      return ordem.desc ? -c : c;
    });
    return ls;
  }, [m.data, ordem]);

  const ok = linhas.filter((l) => l.aluguel_estimado != null);
  const ordenar = (col: Ordem["col"]) =>
    setOrdem((o) => ({ col, desc: o.col === col ? !o.desc : true }));
  const exportar = () =>
    baixar("previsoes_aluguel.csv", [
      [...COLUNAS, "aluguel_estimado", "erro"],
      ...linhas.map((l) => [...COLUNAS.map((c) => l[c]), l.aluguel_estimado, l.erro]),
    ]);

  return (
    <>
      <PageHeader eyebrow="São Paulo · modelo de aluguel" title="Avaliação em lote">
        Envie um CSV com até {MAX_LINHAS} imóveis e receba o aluguel estimado de cada um. Linhas com
        problema são marcadas com o motivo, sem interromper as demais.
      </PageHeader>

      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <div className="space-y-4">
          <Card
            onDragOver={(e) => {
              e.preventDefault();
              setArrastando(true);
            }}
            onDragLeave={() => setArrastando(false)}
            onDrop={soltar}
            className={`flex cursor-pointer flex-col items-center gap-3 border-dashed p-8 text-center transition-colors ${arrastando ? "border-primary bg-primary-soft" : ""}`}
            onClick={() => input.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
          >
            <span className="flex size-10 items-center justify-center rounded-full bg-primary-soft text-primary">
              <Upload className="size-5" />
            </span>
            <div>
              <p className="text-sm font-medium">Arraste o CSV aqui ou clique para escolher</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Separador vírgula ou ponto e vírgula · até {MAX_LINHAS} linhas
              </p>
            </div>
            {arquivo && (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <FileSpreadsheet className="size-3.5" />
                {arquivo.name}
              </p>
            )}
            <input
              ref={input}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => {
                escolher(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
          </Card>
          <Card className="p-4">
            <h3 className="text-sm font-semibold">Formato do arquivo</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Uma linha por imóvel com as colunas{" "}
              <span className="font-mono">{COLUNAS.join(", ")}</span>. Tipo: apartamento, studio,
              casa ou casa_condominio. Campos sim/não: true ou false.
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => baixar("modelo_lote_aluguel.csv", [[...COLUNAS], ...EXEMPLO])}
            >
              <Download className="size-3.5" /> Baixar modelo de CSV
            </Button>
          </Card>
        </div>

        <div className="min-w-0">
          {m.isPending ? (
            <Card className="p-6">
              <div className="flex items-center gap-2 text-sm">
                <Loader2 className="size-4 animate-spin" /> Geocodificando e estimando…
              </div>
              <Progress value={null} className="mt-4 [&>div]:w-1/3 [&>div]:animate-pulse" />
              <p className="mt-3 text-xs text-muted-foreground">
                Cada endereço é localizado e cruzado com os pontos de interesse; leva alguns
                segundos.
              </p>
            </Card>
          ) : m.isError ? (
            <ErrorState error={m.error} onRetry={() => arquivo && m.mutate(arquivo)} />
          ) : m.data ? (
            <div className="space-y-4">
              <Card className="grid grid-cols-3 gap-4 p-5">
                <Metric label="Imóveis" value={fmtNum(linhas.length)} />
                <Metric
                  label="Estimados"
                  value={fmtNum(ok.length)}
                  hint={
                    linhas.length - ok.length ? `${linhas.length - ok.length} com erro` : "todos ok"
                  }
                />
                <Metric
                  label="Aluguel mediano"
                  value={ok.length ? fmtBRL(mediana(ok.map((l) => l.aluguel_estimado!))) : "—"}
                />
              </Card>
              <Card className="p-0">
                <div className="flex items-center justify-between border-b px-4 py-3">
                  <h3 className="text-sm font-semibold">Resultados</h3>
                  <Button size="sm" variant="outline" onClick={exportar}>
                    <Download className="size-3.5" /> Exportar CSV
                  </Button>
                </div>
                <div className="max-h-[560px] overflow-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <Cab col="endereco" ordem={ordem} onClick={ordenar}>
                          Endereço
                        </Cab>
                        <TableHead>Tipo</TableHead>
                        <Cab col="area" ordem={ordem} onClick={ordenar} direita>
                          Área
                        </Cab>
                        <TableHead className="text-right">Anunciado</TableHead>
                        <Cab col="aluguel_estimado" ordem={ordem} onClick={ordenar} direita>
                          Estimado
                        </Cab>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {linhas.map((l, i) => (
                        <TableRow key={i}>
                          <TableCell className="max-w-[280px]">
                            <div className="truncate">{l.endereco}</div>
                            {l.erro && (
                              <div className="truncate text-xs text-critical">{l.erro}</div>
                            )}
                          </TableCell>
                          <TableCell className="text-muted-foreground">{l.tipo}</TableCell>
                          <TableCell className="num text-right">
                            {l.area ? `${fmtNum(l.area)} m²` : "—"}
                          </TableCell>
                          <TableCell className="num text-right text-muted-foreground">
                            {l.aluguel_anunciado ? fmtBRL(l.aluguel_anunciado) : "—"}
                          </TableCell>
                          <TableCell className="num text-right font-medium">
                            {l.aluguel_estimado != null ? fmtBRL(l.aluguel_estimado) : "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </Card>
            </div>
          ) : (
            <EmptyState
              icon={<FileSpreadsheet className="size-6" />}
              title="Nenhum arquivo enviado"
            >
              Baixe o modelo de CSV, preencha com seus imóveis e envie para ver as estimativas.
            </EmptyState>
          )}
        </div>
      </div>
    </>
  );
}

function mediana(v: number[]) {
  const s = [...v].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
}

function Cab({
  col,
  ordem,
  onClick,
  direita,
  children,
}: {
  col: Ordem["col"];
  ordem: Ordem;
  onClick: (c: Ordem["col"]) => void;
  direita?: boolean;
  children: string;
}) {
  const ativo = ordem.col === col;
  return (
    <TableHead
      className={direita ? "text-right" : ""}
      aria-sort={ativo ? (ordem.desc ? "descending" : "ascending") : "none"}
    >
      <button
        type="button"
        onClick={() => onClick(col)}
        className={`inline-flex items-center gap-1 ${ativo ? "text-foreground" : ""}`}
      >
        {children} <ArrowDownUp className="size-3" />
      </button>
    </TableHead>
  );
}

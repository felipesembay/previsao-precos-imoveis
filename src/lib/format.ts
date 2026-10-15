const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const num = new Intl.NumberFormat("pt-BR");
const pct = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export const fmtBRL = (v: number) => brl.format(v);
export const fmtNum = (v: number) => num.format(v);
export const fmtPct = (v: number) => `${pct.format(v)}%`;
export const fmtArea = (v: number) => `${num.format(v)} m²`;
export const fmtDist = (m: number) =>
  m < 1000 ? `${Math.round(m)} m` : `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(m / 1000)} km`;
export const fmtData = (iso: string) =>
  new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
export const fmtBytes = (b: number) => {
  const gb = b / 1024 ** 3;
  return gb >= 1 ? `${pct.format(gb)} GB` : `${num.format(Math.round(b / 1024 ** 2))} MB`;
};

/** Classifica o aluguel anunciado frente ao estimado: tolerância de ±10%. */
export function classificar(anunciado: number, estimado: number) {
  const diferenca_pct = ((anunciado - estimado) / estimado) * 100;
  const classificacao: "abaixo" | "dentro" | "acima" =
    diferenca_pct < -10 ? "abaixo" : diferenca_pct > 10 ? "acima" : "dentro";
  return { aluguel_anunciado: anunciado, diferenca_pct, classificacao };
}

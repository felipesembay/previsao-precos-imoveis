import * as mock from "./mocks";

export type TipoImovel = "apartamento" | "studio" | "casa" | "casa_condominio";

export interface AluguelRequest {
  endereco: string;
  tipo: TipoImovel;
  area: number;
  quartos: number;
  banheiros: number;
  suites: number;
  vagas: number;
  mobiliado: boolean;
  ar_condicionado: boolean;
  piscina: boolean;
  academia: boolean;
  varanda: boolean;
  aluguel_anunciado?: number;
}
export interface Localizacao { lat: number; lon: number; endereco_formatado: string }
export interface Poi { categoria: string; nome: string | null; lat: number; lon: number; distancia_m: number }
export interface ModeloRef { nome: string; versao: string }
export interface Comparacao { aluguel_anunciado: number; diferenca_pct: number; classificacao: "abaixo" | "dentro" | "acima" }

export interface AluguelResponse {
  aluguel_estimado: number;
  faixa: { min: number; max: number };
  custo_extra_pct: number;
  custo_total_estimado: number;
  bairro: string | null;
  localizacao: Localizacao;
  pois_proximos: Poi[];
  comparacao: Comparacao | null;
  modelo: ModeloRef;
}
export interface CompraRequest { endereco: string; area: number; quartos: number; banheiros: number; vagas: number }
export interface CompraResponse {
  preco_estimado: number;
  faixa: { min: number; max: number };
  localizacao: Localizacao;
  pois_proximos: Poi[];
  modelo: ModeloRef;
}
export type LinhaLote = AluguelRequest & { aluguel_estimado: number | null; erro: string | null };
export interface LoteResponse { linhas: LinhaLote[] }
export interface Modelo {
  chave: "aluguel" | "compra";
  nome: string;
  versao: string;
  treinado_em: string;
  n_treino: number;
  metricas: { r2: number; mae_reais: number; mape: number };
}
export interface ModelosResponse { modelos: Modelo[] }
export interface MonitoramentoResponse {
  mape_serie: { data: string; mape: number }[];
  mape_limite: number;
  drift: { feature: string; score: number; status: "ok" | "atencao" | "critico" }[];
  n_amostras: number;
  alertas: { nome: string; severidade: "warning" | "critical"; desde: string; resumo: string }[];
}
export interface Retreino {
  data: string;
  versao_challenger: string;
  versao_champion: string | null;
  mape_challenger: number;
  mape_champion: number | null;
  promovido: boolean;
  motivo: string;
}
export interface RetreinosResponse { retreinos: Retreino[] }
export interface Regiao { nome: string; lat: number; lon: number; n_anuncios: number; aluguel_m2_mediano: number; aluguel_mediano: number }
export interface RegioesResponse { regioes: Regiao[] }
export interface AchadosResponse { achados: { titulo: string; valor: string; descricao: string }[] }
export interface InfraResponse {
  horas_mes: number;
  horas_limite: number;
  banco_bytes: number;
  banco_limite_bytes: number;
  insercoes_24h: number;
  previsoes_total: number;
}

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";
export const USE_MOCKS = (import.meta.env.VITE_USE_MOCKS ?? "true") !== "false";

const delay = <T,>(fn: () => T, ms = 600) =>
  new Promise<T>((resolve, reject) =>
    setTimeout(() => {
      try {
        resolve(fn());
      } catch (e) {
        reject(e);
      }
    }, ms),
  );

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    let msg = `Erro ${res.status}`;
    try {
      const j = await res.json();
      msg = j.detail ?? j.message ?? msg;
    } catch {
      /* ignore */
    }
    throw new Error(typeof msg === "string" ? msg : `Erro ${res.status}`);
  }
  return res.json() as Promise<T>;
}
const post = <T,>(path: string, body: unknown) =>
  http<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  preverAluguel: (r: AluguelRequest) =>
    USE_MOCKS ? delay(() => mock.preverAluguel(r)) : post<AluguelResponse>("/aluguel/prever", r),
  preverCompra: (r: CompraRequest) =>
    USE_MOCKS ? delay(() => mock.preverCompra(r)) : post<CompraResponse>("/compra/prever", r),
  preverLote: async (arquivo: File): Promise<LoteResponse> => {
    if (USE_MOCKS) {
      const text = await arquivo.text();
      return delay(() => mock.preverLote(text), 1200);
    }
    const fd = new FormData();
    fd.append("arquivo", arquivo);
    return http<LoteResponse>("/aluguel/prever-lote", { method: "POST", body: fd });
  },
  modelos: () => (USE_MOCKS ? delay(mock.modelos) : http<ModelosResponse>("/modelos")),
  monitoramento: () => (USE_MOCKS ? delay(mock.monitoramento) : http<MonitoramentoResponse>("/monitoramento/aluguel")),
  retreinos: () => (USE_MOCKS ? delay(mock.retreinos) : http<RetreinosResponse>("/retreinos")),
  regioes: () => (USE_MOCKS ? delay(mock.regioes) : http<RegioesResponse>("/mercado/aluguel/regioes")),
  achados: () => (USE_MOCKS ? delay(mock.achados) : http<AchadosResponse>("/mercado/aluguel/achados")),
  infra: () => (USE_MOCKS ? delay(mock.infra) : http<InfraResponse>("/infra/uso")),
};

export const qk = {
  modelos: ["modelos"],
  monitoramento: ["monitoramento", "aluguel"],
  retreinos: ["retreinos"],
  regioes: ["mercado", "regioes"],
  achados: ["mercado", "achados"],
  infra: ["infra"],
} as const;

import type {
  AchadosResponse, AluguelRequest, AluguelResponse, CompraRequest, CompraResponse, InfraResponse,
  LinhaLote, LoteResponse, ModelosResponse, MonitoramentoResponse, Poi, RegioesResponse, RetreinosResponse, TipoImovel,
} from "./api";
import { classificar } from "./format";

function hash(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}
function rng(seed: number) {
  let a = seed || 1;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const REGIOES_SP = [
  { nome: "Pinheiros", lat: -23.5666, lon: -46.6936, m2: 82, n: 1840, extra: 32 },
  { nome: "Vila Madalena", lat: -23.5534, lon: -46.6911, m2: 78, n: 1120, extra: 30 },
  { nome: "Itaim Bibi", lat: -23.5845, lon: -46.6795, m2: 91, n: 1560, extra: 38 },
  { nome: "Jardins", lat: -23.5686, lon: -46.6631, m2: 88, n: 1710, extra: 40 },
  { nome: "Moema", lat: -23.6009, lon: -46.6658, m2: 76, n: 1290, extra: 36 },
  { nome: "Vila Mariana", lat: -23.5891, lon: -46.6342, m2: 68, n: 1480, extra: 31 },
  { nome: "Bela Vista", lat: -23.5617, lon: -46.6472, m2: 66, n: 1370, extra: 28 },
  { nome: "Consolação", lat: -23.5531, lon: -46.6575, m2: 72, n: 1010, extra: 29 },
  { nome: "Perdizes", lat: -23.5365, lon: -46.6782, m2: 63, n: 980, extra: 30 },
  { nome: "Santana", lat: -23.5025, lon: -46.6249, m2: 48, n: 870, extra: 25 },
  { nome: "Tatuapé", lat: -23.5403, lon: -46.5767, m2: 52, n: 1150, extra: 27 },
  { nome: "Mooca", lat: -23.5596, lon: -46.5992, m2: 50, n: 910, extra: 26 },
  { nome: "Butantã", lat: -23.5717, lon: -46.7083, m2: 54, n: 760, extra: 24 },
  { nome: "Santo Amaro", lat: -23.6545, lon: -46.7101, m2: 49, n: 820, extra: 26 },
  { nome: "República", lat: -23.5432, lon: -46.6424, m2: 61, n: 1190, extra: 22 },
  { nome: "Brooklin", lat: -23.6131, lon: -46.6883, m2: 74, n: 1040, extra: 35 },
  { nome: "Itaquera", lat: -23.5397, lon: -46.4569, m2: 32, n: 540, extra: 18 },
  { nome: "Campo Limpo", lat: -23.6341, lon: -46.7623, m2: 34, n: 480, extra: 19 },
];

const NOMES: Record<string, string[]> = {
  metro: ["Estação Fradique Coutinho", "Estação Faria Lima", "Estação Oscar Freire", "Estação Paraíso", "Estação Sumaré"],
  escola_publica: ["E.E. Prof. Alberto Levy", "EMEF Pres. Campos Salles", "E.E. Fernão Dias"],
  escola_privada: ["Colégio Santa Cruz", "Colégio Bandeirantes", "Escola Vera Cruz"],
  hospital: ["Hospital das Clínicas", "Hospital Sírio-Libanês", "Hospital São Camilo"],
  farmacia: ["Drogasil", "Droga Raia", "Drogaria São Paulo", "Pague Menos"],
  mercado: ["Pão de Açúcar", "Carrefour Express", "St Marche", "Oba Hortifruti"],
  parque: ["Praça Benedito Calixto", "Parque Villa-Lobos", "Parque do Ibirapuera"],
  delegacia: ["14º DP Pinheiros", "15º DP Itaim Bibi", "78º DP Jardins"],
};

function gerarPois(lat: number, lon: number, r: () => number): Poi[] {
  const out: Poi[] = [];
  for (const [cat, nomes] of Object.entries(NOMES)) {
    const n = cat === "metro" || cat === "delegacia" ? 1 + Math.floor(r() * 2) : 2 + Math.floor(r() * 2);
    for (let i = 0; i < n; i++) {
      const ang = r() * Math.PI * 2;
      const d = 120 + r() * (cat === "parque" ? 1600 : 1100);
      const dlat = (d * Math.cos(ang)) / 111320;
      const dlon = (d * Math.sin(ang)) / (111320 * Math.cos((lat * Math.PI) / 180));
      out.push({
        categoria: cat,
        nome: r() < 0.1 ? null : (nomes[Math.floor(r() * nomes.length)] ?? null),
        lat: lat + dlat,
        lon: lon + dlon,
        distancia_m: Math.round(d),
      });
    }
  }
  return out.sort((a, b) => a.distancia_m - b.distancia_m);
}

function localizar(endereco: string) {
  if (!endereco.trim()) throw new Error("Informe um endereço.");
  if (/erro|xxx/i.test(endereco)) throw new Error("Não foi possível localizar esse endereço. Verifique e tente novamente.");
  const h = hash(endereco.toLowerCase());
  const r = rng(h);
  const reg = REGIOES_SP[h % REGIOES_SP.length]!;
  const lat = reg.lat + (r() - 0.5) * 0.012;
  const lon = reg.lon + (r() - 0.5) * 0.012;
  return { reg, r, lat, lon };
}

const TIPO_FATOR: Record<TipoImovel, number> = { apartamento: 1, studio: 1.18, casa: 0.86, casa_condominio: 0.95 };

export function estimarAluguel(req: AluguelRequest, m2: number) {
  let v = req.area * m2 * TIPO_FATOR[req.tipo];
  v *= 1 + req.vagas * 0.04 + req.suites * 0.03 + Math.max(0, req.banheiros - 1) * 0.02;
  if (req.mobiliado) v *= 1.15;
  if (req.ar_condicionado) v *= 1.04;
  if (req.piscina) v *= 1.05;
  if (req.academia) v *= 1.03;
  if (req.varanda) v *= 1.03;
  return Math.round(v / 10) * 10;
}

export function preverAluguel(req: AluguelRequest): AluguelResponse {
  if (!(req.area > 0)) throw new Error("Área deve ser maior que zero.");
  const { reg, r, lat, lon } = localizar(req.endereco);
  const est = estimarAluguel(req, reg.m2);
  return {
    aluguel_estimado: est,
    faixa: { min: Math.round((est * 0.87) / 10) * 10, max: Math.round((est * 1.13) / 10) * 10 },
    custo_extra_pct: reg.extra,
    custo_total_estimado: Math.round(est * (1 + reg.extra / 100)),
    bairro: reg.nome,
    localizacao: { lat, lon, endereco_formatado: `${req.endereco.trim()} — ${reg.nome}, São Paulo - SP` },
    pois_proximos: gerarPois(lat, lon, r),
    comparacao: req.aluguel_anunciado ? classificar(req.aluguel_anunciado, est) : null,
    modelo: { nome: "aluguel-sp-lgbm", versao: "v14" },
  };
}

export function preverCompra(req: CompraRequest): CompraResponse {
  if (!req.endereco.trim()) throw new Error("Informe um endereço.");
  const h = hash(req.endereco.toLowerCase());
  const r = rng(h);
  const lat = -25.0945 + (r() - 0.5) * 0.05;
  const lon = -50.1633 + (r() - 0.5) * 0.05;
  const m2 = 4200 + r() * 2600;
  const preco = Math.round((req.area * m2 * (1 + req.vagas * 0.05 + req.quartos * 0.02)) / 1000) * 1000;
  return {
    preco_estimado: preco,
    faixa: { min: Math.round(preco * 0.88), max: Math.round(preco * 1.12) },
    localizacao: { lat, lon, endereco_formatado: `${req.endereco.trim()} — Ponta Grossa - PR` },
    pois_proximos: gerarPois(lat, lon, r).filter((p) => p.categoria !== "metro"),
    modelo: { nome: "compra-pg-xgb", versao: "v6" },
  };
}

const bool = (s: string | undefined) => /^(1|true|sim|s|yes)$/i.test((s ?? "").trim());

export function preverLote(csv: string): LoteResponse {
  const lines = csv.split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) throw new Error("O CSV não tem linhas de dados.");
  const sep = lines[0]!.includes(";") ? ";" : ",";
  const head = lines[0]!.split(sep).map((h) => h.trim().toLowerCase());
  const linhas: LinhaLote[] = lines.slice(1).map((l) => {
    const c = l.split(sep);
    const g = (k: string) => c[head.indexOf(k)]?.trim();
    const n = (k: string) => Number(g(k) ?? 0) || 0;
    const req: AluguelRequest = {
      endereco: g("endereco") ?? "",
      tipo: ((g("tipo") as TipoImovel) || "apartamento"),
      area: n("area"), quartos: n("quartos"), banheiros: n("banheiros"), suites: n("suites"), vagas: n("vagas"),
      mobiliado: bool(g("mobiliado")), ar_condicionado: bool(g("ar_condicionado")), piscina: bool(g("piscina")),
      academia: bool(g("academia")), varanda: bool(g("varanda")),
      aluguel_anunciado: n("aluguel_anunciado") || undefined,
    };
    try {
      if (!TIPO_FATOR[req.tipo]) throw new Error(`Tipo inválido: ${req.tipo}`);
      const res = preverAluguel(req);
      return { ...req, aluguel_estimado: res.aluguel_estimado, erro: null };
    } catch (e) {
      return { ...req, aluguel_estimado: null, erro: e instanceof Error ? e.message : "Erro" };
    }
  });
  return { linhas };
}

export const modelos = (): ModelosResponse => ({
  modelos: [
    { chave: "aluguel", nome: "aluguel-sp-lgbm", versao: "v14", treinado_em: "2026-10-06T03:00:00Z", n_treino: 22184, metricas: { r2: 0.874, mae_reais: 612, mape: 12.4 } },
    { chave: "compra", nome: "compra-pg-xgb", versao: "v6", treinado_em: "2026-09-22T03:00:00Z", n_treino: 4930, metricas: { r2: 0.851, mae_reais: 38400, mape: 14.1 } },
  ],
});

export const monitoramento = (): MonitoramentoResponse => {
  const r = rng(42);
  const serie = Array.from({ length: 30 }, (_, i) => {
    const d = new Date(Date.UTC(2026, 8, 15 + i));
    const base = i < 21 ? 12.2 + i * 0.12 : 11.9 + (i - 21) * 0.15;
    return { data: d.toISOString().slice(0, 10), mape: +(base + (r() - 0.5) * 1.2).toFixed(2) };
  });
  return {
    mape_serie: serie,
    mape_limite: 15,
    n_amostras: 3418,
    drift: [
      { feature: "area", score: 0.04, status: "ok" },
      { feature: "aluguel_m2_bairro", score: 0.21, status: "atencao" },
      { feature: "dist_metro_m", score: 0.06, status: "ok" },
      { feature: "quartos", score: 0.03, status: "ok" },
      { feature: "mobiliado", score: 0.32, status: "critico" },
      { feature: "vagas", score: 0.08, status: "ok" },
      { feature: "n_pois_500m", score: 0.14, status: "atencao" },
      { feature: "tipo", score: 0.05, status: "ok" },
    ],
    alertas: [
      { nome: "FeatureDriftCritico", severidade: "critical", desde: "2026-10-13T08:12:00Z", resumo: "PSI da feature 'mobiliado' acima de 0,25 nos últimos 7 dias." },
      { nome: "MapeSubindo", severidade: "warning", desde: "2026-10-14T02:00:00Z", resumo: "MAPE móvel de 7 dias subiu 0,8 p.p. em relação à semana anterior." },
    ],
  };
};

export const retreinos = (): RetreinosResponse => ({
  retreinos: [
    { data: "2026-10-06T03:00:00Z", versao_challenger: "v14", versao_champion: "v13", mape_challenger: 12.4, mape_champion: 13.6, promovido: true, motivo: "MAPE 1,2 p.p. menor no conjunto de validação temporal." },
    { data: "2026-09-29T03:00:00Z", versao_challenger: "v13b", versao_champion: "v13", mape_challenger: 13.9, mape_champion: 13.6, promovido: false, motivo: "Challenger pior que o champion; mantido v13." },
    { data: "2026-09-22T03:00:00Z", versao_challenger: "v13", versao_champion: "v12", mape_challenger: 13.6, mape_champion: 14.8, promovido: true, motivo: "Drift em 'aluguel_m2_bairro' corrigido com dados novos." },
    { data: "2026-09-15T03:00:00Z", versao_challenger: "v12b", versao_champion: "v12", mape_challenger: 14.7, mape_champion: 14.8, promovido: false, motivo: "Ganho abaixo do mínimo de 0,5 p.p. exigido." },
    { data: "2026-09-01T03:00:00Z", versao_challenger: "v12", versao_champion: null, mape_challenger: 14.8, mape_champion: null, promovido: true, motivo: "Primeiro modelo registrado como @champion." },
  ],
});

export const regioes = (): RegioesResponse => ({
  regioes: REGIOES_SP.map((g) => ({
    nome: g.nome, lat: g.lat, lon: g.lon, n_anuncios: g.n, aluguel_m2_mediano: g.m2, aluguel_mediano: Math.round(g.m2 * 62 / 10) * 10,
  })),
});

export const achados = (): AchadosResponse => ({
  achados: [
    { titulo: "Prêmio do metrô", valor: "+11,2%", descricao: "Imóveis a até 500 m de uma estação custam, em média, 11,2% mais por m² que imóveis equivalentes a mais de 1,5 km." },
    { titulo: "Mobiliado vale mais", valor: "+15,0%", descricao: "Mobília completa adiciona cerca de 15% ao aluguel, efeito mais forte em studios." },
    { titulo: "Studios são os mais caros por m²", valor: "R$ 96/m²", descricao: "Studios e kitnets têm o maior R$/m² mediano, cerca de 18% acima dos apartamentos." },
    { titulo: "Custo oculto", valor: "31%", descricao: "Condomínio e IPTU somam em média 31% do aluguel — maior nos Jardins e Itaim Bibi." },
  ],
});

export const infra = (): InfraResponse => ({
  horas_mes: 362,
  horas_limite: 750,
  banco_bytes: 9.4 * 1024 ** 3,
  banco_limite_bytes: 32 * 1024 ** 3,
  insercoes_24h: 1284,
  previsoes_total: 18342,
});

/** Nomes legíveis das features dos modelos (como chegam do monitoramento, em minúsculas). */
const FEATURES: Record<string, string> = {
  bedrooms: "Quartos",
  bathrooms: "Banheiros",
  parkingspaces: "Vagas",
  area: "Área",
  suites: "Suítes",
  mobiliado: "Mobiliado",
  am_ar_condicionado: "Ar-condicionado",
  inst_piscina: "Piscina",
  inst_academia: "Academia",
  am_varanda: "Varanda",
  dist_centro_km: "Distância ao centro",
  dist_polo_km: "Distância a polo de emprego",
  score_escola_privada: "Escolas privadas",
  score_escola_publica: "Escolas públicas",
  score_hospitais: "Hospitais",
  score_mercado: "Mercados",
  score_farmacia: "Farmácias",
  score_parque: "Parques",
  score_seguranca: "Delegacias",
  score_metro: "Metrô",
  area_m2: "Área",
  quartos: "Quartos",
  banheiros: "Banheiros",
  vagas_garagem: "Vagas",
};

export const rotuloFeature = (f: string) => FEATURES[f] ?? f;

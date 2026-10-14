"""
Simula uso em produção da tela de aluguel em lote, para testar drift e desempenho.

Usa anúncios reais (endereço, lat/lon, planta e aluguel do anúncio) do holdout do
@champion — imóveis que o modelo não viu no treino — e passa cada lote pelo mesmo
caminho da tela de lote: POIs → features → modelo @champion → predicoes_aluguel +
features_monitoramento_aluguel. Sem geocoding: a coordenada já vem do anúncio.

Cenário (--cenario):
  normal  todos os lotes sorteados do holdout: não deve haver drift
  drift   lotes com mais imóveis grandes e centrais (área ≥ 100 m², até 8 km da Sé)
          e aluguel anunciado +20% (reajuste de mercado): drift + queda de desempenho
  misto   (padrão) primeira metade normal, segunda metade drift
  forte   só imóveis grandes e centrais (com reposição) e aluguel anunciado +35%:
          leva o MAPE acima do limite de 25% e dispara o gatilho de retreino

As linhas gravadas levam origem = 'sintetico'; --limpar apaga todas.

Uso:
    python scripts/simular_producao_aluguel.py                        # 8 lotes de 250, 10 min entre lotes
    python scripts/simular_producao_aluguel.py --lotes 4 --intervalo 5 --cenario drift
    python scripts/simular_producao_aluguel.py --limpar
"""

import argparse
import os
import subprocess
import sys
import time
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "streamlit_app"))

from aluguel_core import (carregar_custo_extra, carregar_modelo, carregar_pois,  # noqa: E402
                          custo_extra_do_bairro, features_para_monitoramento,
                          montar_registro, prever_aluguel)
from db import get_connection, salvar_features_monitoramento_aluguel, salvar_predicao_aluguel  # noqa: E402
from src.features.aluguel import montar_entrada_modelo  # noqa: E402
from src.models.promover_aluguel import split_do_run  # noqa: E402
from src.models.registro import cliente, versao_champion  # noqa: E402
from src.models.train_aluguel import MODEL_NAME  # noqa: E402

ORIGEM = "sintetico"
REAJUSTE_DRIFT = 1.20
REAJUSTE_FORTE = 1.35
COLS_IMOVEL = ["type", "area", "bedrooms", "bathrooms", "suites", "parkingSpaces", "mobiliado",
               "am_ar_condicionado", "inst_piscina", "inst_academia", "am_varanda"]


def anuncios_ineditos() -> pd.DataFrame:
    """Holdout do @champion + endereço e bairro do bruto da mesma extração."""
    client = cliente()
    run = client.get_run(versao_champion(MODEL_NAME, client).run_id)
    _, teste = split_do_run(run)

    raw_path = run.data.params["data_path"].replace("data/interim/aluguel_sp_features_",
                                                    "data/raw/quintoandar/quintoandar_sp_")
    raw_path = os.path.join(ROOT, raw_path)
    if os.path.exists(raw_path):
        raw = pd.read_parquet(raw_path, columns=["id", "address", "neighbourhood"])
        teste = teste.merge(raw, on="id", how="left")
    else:  # dataset dos notebooks: endereço já está nele
        teste = teste.assign(address=teste.get("address"), neighbourhood=teste.get("neighbourhood"))
    return teste.reset_index(drop=True)


def sortear_lote(base: pd.DataFrame, n: int, drift: bool, rng, forte: bool = False) -> pd.DataFrame:
    if forte:
        alvo = base[(base["area"] >= 100) & (base["dist_centro_km"] <= 8)]
        lote = alvo.sample(n, replace=True, random_state=rng)
        return lote.assign(aluguel_anuncio=lote["rent"] * REAJUSTE_FORTE)
    if drift:
        alvo = (base["area"] >= 100) & (base["dist_centro_km"] <= 8)
        pesos = np.where(alvo, 12.0, 1.0)
        lote = base.sample(n, weights=pesos, random_state=rng)
        return lote.assign(aluguel_anuncio=lote["rent"] * REAJUSTE_DRIFT)
    lote = base.sample(n, random_state=rng)
    return lote.assign(aluguel_anuncio=lote["rent"])


def gravar_lote(lote: pd.DataFrame, modelo, versao, pois, tabela_custo) -> tuple[int, float]:
    entradas = [montar_entrada_modelo(r.lat, r.lon, {c: getattr(r, c) for c in COLS_IMOVEL}, pois)
                for r in lote.itertuples()]
    entrada = pd.concat(entradas, ignore_index=True)
    entrada["aluguel_predito"] = prever_aluguel(modelo, entrada)

    erros = []
    for n, row in enumerate(lote.itertuples()):
        linha = entrada.iloc[[n]]
        pct = None
        if tabela_custo is not None:
            pct = float(custo_extra_do_bairro(row.neighbourhood, tabela_custo)[0]["pct_extra_mediana"])
        geo = {"lat": row.lat, "lng": row.lon, "endereco_formatado": row.address, "bairro": row.neighbourhood}
        registro = montar_registro(geo, {c: getattr(row, c) for c in COLS_IMOVEL}, linha,
                                   float(linha["aluguel_predito"].iloc[0]), row.aluguel_anuncio,
                                   pct, versao, origem=ORIGEM)
        predicao_id = salvar_predicao_aluguel(registro)
        salvar_features_monitoramento_aluguel(predicao_id, features_para_monitoramento(linha))
        erros.append(registro["erro_percentual"])
    return len(lote), float(np.mean(erros))


def limpar():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""DELETE FROM features_monitoramento_aluguel WHERE predicao_id IN
                           (SELECT id FROM predicoes_aluguel WHERE origem = %s)""", (ORIGEM,))
            cur.execute("DELETE FROM predicoes_aluguel WHERE origem = %s", (ORIGEM,))
            print(f"🧹 {cur.rowcount} previsões sintéticas apagadas")
        conn.commit()


def main(lotes: int, tamanho: int, intervalo_min: float, cenario: str, monitorar: bool, seed: int):
    rng = np.random.default_rng(seed)
    base = anuncios_ineditos()
    base["mobiliado"] = base["mobiliado"].astype(int)
    modelo, versao, _ = carregar_modelo()
    pois, tabela_custo = carregar_pois(), carregar_custo_extra()
    print(f"🏠 {len(base):,} anúncios inéditos para o {MODEL_NAME} v{versao} | "
          f"{lotes} lotes de {tamanho} a cada {intervalo_min:g} min | cenário {cenario}", flush=True)

    for i in range(lotes):
        drift = cenario in ("drift", "forte") or (cenario == "misto" and i >= lotes // 2)
        lote = sortear_lote(base, tamanho, drift, rng, forte=cenario == "forte")
        n, mape = gravar_lote(lote, modelo, versao, pois, tabela_custo)
        rotulo = cenario if cenario == "forte" else ("drift" if drift else "normal")
        print(f"[{time.strftime('%H:%M:%S')}] lote {i + 1}/{lotes} ({rotulo}): "
              f"{n} previsões, MAPE do lote {mape:.1%}, área média {lote['area'].mean():.0f} m²", flush=True)

        if monitorar:
            subprocess.run([sys.executable, os.path.join(ROOT, "monitoring/jobs/run_data_drift.py"), "aluguel"],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("   ↳ monitoramento atualizado (Grafana em até 1 min)", flush=True)

        if i < lotes - 1:
            time.sleep(intervalo_min * 60)
    print("✅ Simulação concluída", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--lotes", type=int, default=8)
    p.add_argument("--tamanho", type=int, default=250)
    p.add_argument("--intervalo", type=float, default=10, help="minutos entre lotes")
    p.add_argument("--cenario", choices=["normal", "drift", "misto", "forte"], default="misto")
    p.add_argument("--sem-monitoramento", action="store_true", help="não roda o job de drift após cada lote")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limpar", action="store_true", help="apaga as previsões sintéticas e sai")
    a = p.parse_args()
    if a.limpar:
        limpar()
    else:
        main(a.lotes, a.tamanho, a.intervalo, a.cenario, not a.sem_monitoramento, a.seed)

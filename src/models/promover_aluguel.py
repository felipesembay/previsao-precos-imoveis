"""
Champion × challenger do modelo de aluguel.

O challenger (versão recém-treinada) e o @champion atual são avaliados no MESMO
holdout: o teste do challenger, refeito a partir do data_path e do split logados
no run, sem os anúncios que estavam no treino do champion. O mesmo imóvel continua
anunciado entre duas extrações (~30% do holdout no 1º retreino); sem esse filtro o
champion seria avaliado em dados que já viu e quase nunca perderia.
O challenger vira @champion só se tiver MAPE em R$ menor.

Toda decisão é gravada em retreinos_modelo (PostgreSQL) e como tags na versão.
Se promover, regenera o baseline de drift com os dados do novo champion.

Uso:
    python -m src.models.promover_aluguel 3                      # avalia a v3
    python -m src.models.promover_aluguel --dataset data/interim/X.parquet --motivo "drift"
        (avalia a versão mais recente treinada com esse dataset — usado pela DAG)
"""

import argparse
import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import mlflow.sklearn  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

from src.features.aluguel import CAT_FEATURES, NUM_FEATURES, TARGET, prepare_dataset  # noqa: E402
from src.models.registro import ALIAS_CHAMPION, cliente, versao_champion  # noqa: E402
from src.models.train_aluguel import DATA_PATH, MODEL_NAME, eval_metrics  # noqa: E402


def split_do_run(run) -> tuple:
    """Refaz (treino, teste) do run a partir de data_path, test_size e random_state logados."""
    p = run.data.params
    caminho = os.path.join(_ROOT, p["data_path"]) if "data_path" in p else DATA_PATH  # runs antigos
    df = prepare_dataset(caminho)
    return train_test_split(df, test_size=float(p["test_size"]), random_state=int(p["random_state"]))


def avaliar(versao: str, X_test, y_test) -> dict:
    modelo = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}/{versao}")
    return eval_metrics(y_test, modelo.predict(X_test))


def versao_do_dataset(client, dataset: str) -> str:
    """Versão mais recente cujo run foi treinado com ``dataset``."""
    alvo = os.path.relpath(os.path.abspath(dataset), _ROOT)
    versoes = [v for v in client.search_model_versions(f"name='{MODEL_NAME}'")
               if client.get_run(v.run_id).data.params.get("data_path") == alvo]
    if not versoes:
        raise ValueError(f"Nenhuma versão de {MODEL_NAME} treinada com {alvo}")
    return max(versoes, key=lambda v: int(v.version)).version


def main(versao_challenger: str, motivo: str = "") -> dict:
    client = cliente()
    challenger = client.get_model_version(MODEL_NAME, versao_challenger)
    run = client.get_run(challenger.run_id)
    champion = versao_champion(MODEL_NAME, client, excluir=challenger.version)
    if champion is not None and champion.version == challenger.version:
        champion = None  # primeira versão com alias: não há com quem comparar

    _, teste = split_do_run(run)
    n_holdout = len(teste)
    if champion:
        treino_champion, _ = split_do_run(client.get_run(champion.run_id))
        teste = teste[~teste["id"].isin(treino_champion["id"])]
    X_test, y_test = teste[NUM_FEATURES + CAT_FEATURES], teste[TARGET]
    m_chal = avaliar(challenger.version, X_test, y_test)
    m_champ = avaliar(champion.version, X_test, y_test) if champion else None

    promovido = m_champ is None or m_chal["mape_reais"] < m_champ["mape_reais"]

    resultado = {
        "modelo": MODEL_NAME,
        "versao_challenger": challenger.version,
        "versao_champion": champion.version if champion else None,
        "mape_challenger": m_chal["mape_reais"],
        "mape_champion": m_champ["mape_reais"] if m_champ else None,
        "mae_challenger": m_chal["mae_reais"],
        "mae_champion": m_champ["mae_reais"] if m_champ else None,
        "r2_challenger": m_chal["r2"],
        "r2_champion": m_champ["r2"] if m_champ else None,
        "n_teste": len(y_test),
        "dataset": run.data.params["data_path"],
        "motivo": motivo,
        "promovido": promovido,
    }

    print(f"🥊 Holdout do challenger: {len(y_test):,} de {n_holdout:,} anúncios "
          f"(fora do treino do champion) — {resultado['dataset']}")
    print(f"   challenger v{challenger.version}: MAPE {m_chal['mape_reais']:.2%} | MAE R$ {m_chal['mae_reais']:,.0f}")
    if m_champ:
        print(f"   champion   v{champion.version}: MAPE {m_champ['mape_reais']:.2%} | MAE R$ {m_champ['mae_reais']:,.0f}")

    client.set_model_version_tag(MODEL_NAME, challenger.version, "decisao", "promovido" if promovido else "rejeitado")
    client.set_model_version_tag(MODEL_NAME, challenger.version, "mape_holdout", f"{m_chal['mape_reais']:.4f}")
    if m_champ:
        client.set_model_version_tag(MODEL_NAME, challenger.version, "mape_champion_holdout",
                                     f"{m_champ['mape_reais']:.4f}")

    if promovido:
        client.set_registered_model_alias(MODEL_NAME, ALIAS_CHAMPION, challenger.version)
        print(f"🏆 v{challenger.version} promovida a @{ALIAS_CHAMPION}")
        from monitoring.jobs.generate_baseline_aluguel import gerar_baseline
        gerar_baseline()
    else:
        print(f"↩️  v{challenger.version} rejeitada; @{ALIAS_CHAMPION} continua v{champion.version}")

    from monitoring.db.postgres import save_retreino
    save_retreino(resultado)
    return resultado


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("versao", nargs="?", help="versão do challenger no Model Registry")
    parser.add_argument("--dataset", help="alternativa à versão: parquet com que o challenger foi treinado")
    parser.add_argument("--motivo", default="", help="gatilho do retreino (vai para retreinos_modelo)")
    args = parser.parse_args()
    if not (args.versao or args.dataset):
        parser.error("informe a versão ou --dataset")
    versao = args.versao or versao_do_dataset(cliente(), args.dataset)
    print(json.dumps(main(versao, args.motivo), default=str))

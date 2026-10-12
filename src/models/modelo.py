"""
Modelos de Regressão para Previsão de Preços de Imóveis
Treina, avalia e salva modelos de machine learning
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
import joblib
import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class ModeloRegressao:
    """
    Classe para treinar e avaliar modelos de regressão
    """
    
    def __init__(self, df: pd.DataFrame, target: str = 'preco_numerico'):
        self.df = df
        self.target = target
        self.X = None
        self.y = None
        self.X_train = None
        self.X_test = None
        self.y_train = None
        self.y_test = None
        self.scaler = StandardScaler()
        self.modelos = {}
        self.resultados = {}
    
    def preparar_dados(self, features: list = None, test_size: float = 0.2, random_state: int = 42):
        """
        Prepara os dados para treinamento
        """
        if features is None:
            # Features padrão
            features = [
                'area_m2', 'quartos', 'banheiros', 
                'preco_por_m2', 'banheiro_por_quarto'
            ]
        
        # Remover linhas com valores faltantes
        df_temp = self.df[features + [self.target]].dropna()
        
        self.X = df_temp[features]
        self.y = df_temp[self.target]
        
        # Dividir em treino e teste
        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(
            self.X, self.y, test_size=test_size, random_state=random_state
        )
        
        # Normalizar features
        self.X_train = self.scaler.fit_transform(self.X_train)
        self.X_test = self.scaler.transform(self.X_test)
        
        logger.info(f"Dados preparados: {len(self.X_train)} treino, {len(self.X_test)} teste")
    
    def treinar_regressao_linear(self):
        """
        Treina modelo de Regressão Linear
        """
        logger.info("Treinando Regressão Linear...")
        modelo = LinearRegression()
        modelo.fit(self.X_train, self.y_train)
        self.modelos['linear'] = modelo
        self._avaliar_modelo('linear', modelo)
    
    def treinar_ridge(self, alpha: float = 1.0):
        """
        Treina modelo Ridge (L2 regularization)
        """
        logger.info(f"Treinando Ridge (alpha={alpha})...")
        modelo = Ridge(alpha=alpha)
        modelo.fit(self.X_train, self.y_train)
        self.modelos['ridge'] = modelo
        self._avaliar_modelo('ridge', modelo)
    
    def treinar_lasso(self, alpha: float = 0.1):
        """
        Treina modelo Lasso (L1 regularization)
        """
        logger.info(f"Treinando Lasso (alpha={alpha})...")
        modelo = Lasso(alpha=alpha)
        modelo.fit(self.X_train, self.y_train)
        self.modelos['lasso'] = modelo
        self._avaliar_modelo('lasso', modelo)
    
    def treinar_random_forest(self, n_estimators: int = 100):
        """
        Treina modelo Random Forest
        """
        logger.info(f"Treinando Random Forest (n_estimators={n_estimators})...")
        modelo = RandomForestRegressor(n_estimators=n_estimators, random_state=42, n_jobs=-1)
        modelo.fit(self.X_train, self.y_train)
        self.modelos['random_forest'] = modelo
        self._avaliar_modelo('random_forest', modelo)
    
    def treinar_gradient_boosting(self, n_estimators: int = 100):
        """
        Treina modelo Gradient Boosting
        """
        logger.info(f"Treinando Gradient Boosting (n_estimators={n_estimators})...")
        modelo = GradientBoostingRegressor(n_estimators=n_estimators, random_state=42)
        modelo.fit(self.X_train, self.y_train)
        self.modelos['gradient_boosting'] = modelo
        self._avaliar_modelo('gradient_boosting', modelo)
    
    def _avaliar_modelo(self, nome: str, modelo):
        """
        Avalia um modelo e armazena métricas
        """
        # Predições
        y_pred_train = modelo.predict(self.X_train)
        y_pred_test = modelo.predict(self.X_test)
        
        # Métricas
        mse_test = mean_squared_error(self.y_test, y_pred_test)
        rmse_test = np.sqrt(mse_test)
        mae_test = mean_absolute_error(self.y_test, y_pred_test)
        r2_test = r2_score(self.y_test, y_pred_test)
        r2_train = r2_score(self.y_train, y_pred_train)
        
        self.resultados[nome] = {
            'rmse': rmse_test,
            'mae': mae_test,
            'r2_score': r2_test,
            'r2_train': r2_train,
            'mse': mse_test
        }
        
        logger.info(
            f"{nome}: RMSE={rmse_test:.2f}, MAE={mae_test:.2f}, "
            f"R²={r2_test:.4f}"
        )
    
    def treinar_todos_modelos(self):
        """
        Treina todos os modelos disponíveis
        """
        logger.info("Iniciando treinamento de todos os modelos...")
        self.treinar_regressao_linear()
        self.treinar_ridge()
        self.treinar_lasso()
        self.treinar_random_forest()
        self.treinar_gradient_boosting()
        logger.info("Treinamento concluído!")
    
    def obter_melhor_modelo(self) -> Tuple[str, Dict]:
        """
        Retorna o melhor modelo baseado em R² score
        """
        if not self.resultados:
            logger.warning("Nenhum modelo foi treinado ainda")
            return None, None
        
        melhor = max(self.resultados.items(), key=lambda x: x[1]['r2_score'])
        logger.info(f"Melhor modelo: {melhor[0]}")
        return melhor
    
    def salvar_melhor_modelo(self, caminho: str = 'models/'):
        """
        Salva o melhor modelo
        """
        melhor_nome, _ = self.obter_melhor_modelo()
        if melhor_nome:
            caminho_completo = f"{caminho}{melhor_nome}_model.joblib"
            joblib.dump(self.modelos[melhor_nome], caminho_completo)
            logger.info(f"Modelo salvo em: {caminho_completo}")
    
    def gerar_relatorio(self) -> pd.DataFrame:
        """
        Gera relatório comparativo dos modelos
        """
        df_relatorio = pd.DataFrame(self.resultados).T
        df_relatorio = df_relatorio.sort_values('r2_score', ascending=False)
        return df_relatorio


def main():
    """
    Função principal para treinar modelos
    """
    # Carregar dados processados
    df = pd.read_csv('data/processed/imoveis_guarapuava_processados.csv')
    
    # Criar instância do modelo
    modelo_ml = ModeloRegressao(df)
    
    # Preparar dados
    modelo_ml.preparar_dados()
    
    # Treinar todos os modelos
    modelo_ml.treinar_todos_modelos()
    
    # Gerar relatório
    df_relatorio = modelo_ml.gerar_relatorio()
    
    print("\n" + "="*60)
    print("COMPARATIVO DE MODELOS")
    print("="*60)
    print(df_relatorio)
    
    # Salvar melhor modelo
    modelo_ml.salvar_melhor_modelo()
    
    # Salvar relatório
    df_relatorio.to_csv('results/comparativo_modelos.csv')
    print("\nRelatório salvo em: results/comparativo_modelos.csv")


if __name__ == "__main__":
    main()

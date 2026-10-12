"""
Pipeline de pré-processamento sklearn.
Reproduz exatamente o pipeline do notebook ML.ipynb:
  - QuantileClipper (outliers)
  - SimpleImputer
  - StandardScaler
  - OneHotEncoder para categóricas
"""

import os
import sys

# Garantir que a raiz do projeto está no sys.path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.features.pipeline import CAT_FEATURES, NUM_FEATURES

# ============================================================
# QuantileClipper — mesmo do ML.ipynb
# ============================================================

class QuantileClipper(BaseEstimator, TransformerMixin):
    """Clipa outliers usando quantis inferior e superior."""

    def __init__(self, lower: float = 0.01, upper: float = 0.99):
        self.lower = lower
        self.upper = upper

    def fit(self, X, y=None):
        X = pd.DataFrame(X)
        self.q_low_ = X.quantile(self.lower)
        self.q_high_ = X.quantile(self.upper)
        return self

    def transform(self, X):
        X = pd.DataFrame(X)
        return X.clip(self.q_low_, self.q_high_, axis=1)


# ============================================================
# Construtor do preprocessor
# ============================================================

def build_preprocessor(
    num_features: list = None,
    cat_features: list = None,
) -> ColumnTransformer:
    """
    Retorna o ColumnTransformer pronto (não fittado).
    Mesma estrutura usada no ML.ipynb.
    """
    if num_features is None:
        num_features = NUM_FEATURES
    if cat_features is None:
        cat_features = CAT_FEATURES

    num_pipeline = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("outliers", QuantileClipper(0.01, 0.99)),
        ("scaler", StandardScaler()),
    ])

    cat_pipeline = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OneHotEncoder(drop="first", handle_unknown="ignore")),
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", num_pipeline, num_features),
            ("cat", cat_pipeline, cat_features),
        ]
    )

    return preprocessor


def get_feature_names(preprocessor, cat_features: list = None) -> list:
    """Extrai os nomes das features após o fit (incluindo OHE)."""
    if cat_features is None:
        cat_features = CAT_FEATURES

    cat_names = list(
        preprocessor
        .named_transformers_["cat"]
        .named_steps["encoder"]
        .get_feature_names_out(cat_features)
    )
    return list(NUM_FEATURES) + cat_names

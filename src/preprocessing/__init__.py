# Compatibilidade: modelos salvos antes da reorganização de pastas referenciam
# `src.preprocessing.QuantileClipper` (quando src/preprocessing.py era um arquivo).
from src.preprocessing.clean import QuantileClipper  # noqa: F401

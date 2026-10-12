# Scripts de Web Scraping - ZapImóveis

## 📋 Visão Geral

Este diretório contém scripts para fazer web scraping do site ZapImóveis e processar os dados coletados.

## 🚀 Scripts Disponíveis

### 1. `src/scraping/zapimoveis/venda.py` - Coletor Principal

Script principal para fazer scraping de imóveis com estratégia anti-bloqueio.

**Localização**: `src/scraping/zapimoveis/venda.py`

**Como usar**:

```bash
conda activate regression
python src/scraping/zapimoveis/venda.py
```

**Inputs solicitados**:
- **Cidade**: Nome da cidade (ex: guarapuava, curitiba)
- **Estado**: Sigla do estado (ex: pr, sp)
- **Número de páginas**: 
  - Digite um número específico (ex: 12)
  - Pressione ENTER para coletar até acabar

**Saídas**:
- **Arquivos individuais**: `data/raw/por_pagina/cidade_estado_paginaN.csv`
- **Arquivo consolidado**: `data/raw/imoveis_cidade_TIMESTAMP.csv`

**Características**:
- ✅ Fecha/reabre navegador entre páginas (evita bloqueio)
- ✅ Delays randomizados (5-10s)
- ✅ Rotação de User-Agents
- ✅ Detecção automática de fim de páginas
- ✅ Salva cada página individualmente

---

### 2. `unir_arquivos.py` - Consolidador de Dados

Script para unir múltiplos arquivos CSV em um único DataFrame.

**Localização**: `data/unir_arquivos.py`

**Como usar**:

```bash
cd data
conda activate regression
python unir_arquivos.py
```

**Opções**:

#### Opção 1: Unir arquivos de uma cidade específica
```
Escolha: 1
Cidade: guarapuava
Estado: pr
```

**Resultado**: `data/raw/imoveis_guarapuava_pr_completo.csv`

#### Opção 2: Unir TODOS os arquivos
```
Escolha: 2
```

**Resultado**: `data/raw/imoveis_todos_completo.csv`

**Funcionalidades**:
- Remove duplicatas automaticamente (baseado no link)
- Mostra estatísticas por cidade
- Valida integridade dos dados

---

## 📁 Estrutura de Arquivos

```
data/
├── raw/
│   ├── por_pagina/              # Arquivos individuais por página
│   │   ├── guarapuava_pr_pagina1.csv
│   │   ├── guarapuava_pr_pagina2.csv
│   │   ├── curitiba_pr_pagina1.csv
│   │   └── ...
│   ├── imoveis_guarapuava_pr_completo.csv    # Consolidado por cidade
│   └── imoveis_todos_completo.csv             # Consolidado geral
└── unir_arquivos.py             # Script de união
```

---

## 💡 Exemplos de Uso

### Exemplo 1: Coletar 12 páginas de Guarapuava

```bash
python src/scraping/zapimoveis/venda.py

# Inputs:
# Cidade: guarapuava
# Estado: pr
# Páginas: 12
```

**Resultado**:
- 12 arquivos: `guarapuava_pr_pagina1.csv` até `guarapuava_pr_pagina12.csv`
- 1 arquivo consolidado: `imoveis_guarapuava_TIMESTAMP.csv`

### Exemplo 2: Coletar até acabar (Curitiba)

```bash
python src/scraping/zapimoveis/venda.py

# Inputs:
# Cidade: curitiba
# Estado: pr
# Páginas: [ENTER]
```

**Resultado**: Coleta automaticamente até encontrar 2 páginas vazias consecutivas

### Exemplo 3: Unir dados de Guarapuava

```bash
cd data
python unir_arquivos.py

# Opção: 1
# Cidade: guarapuava
# Estado: pr
```

**Resultado**: `data/raw/imoveis_guarapuava_pr_completo.csv`

### Exemplo 4: Unir dados de múltiplas cidades

```bash
# 1. Coletar Guarapuava
python src/scraping/zapimoveis/venda.py
# Cidade: guarapuava, Estado: pr, Páginas: 12

# 2. Coletar Curitiba
python src/scraping/zapimoveis/venda.py
# Cidade: curitiba, Estado: pr, Páginas: 20

# 3. Unir tudo
cd data
python unir_arquivos.py
# Opção: 2
```

**Resultado**: `data/raw/imoveis_todos_completo.csv` com dados de ambas as cidades

---

## 🔧 Configurações Avançadas

### Ajustar delays entre páginas

Edite `src/scraping/zapimoveis/venda.py`:

```python
# Linha ~550
DELAY_MIN = 5.0   # Mínimo 5 segundos
DELAY_MAX = 10.0  # Máximo 10 segundos
```

### Modo headless (sem interface gráfica)

```python
# Linha ~552
HEADLESS = True
```

### Desabilitar salvamento por página

```python
# Linha ~560
salvar_por_pagina=False
```

---

## 📊 Formato dos Dados

Cada arquivo CSV contém as seguintes colunas:

| Coluna | Tipo | Descrição | Exemplo |
|--------|------|-----------|---------|
| `preco` | string | Preço do imóvel | "R$ 350.000" |
| `rua` | string | Nome da rua | "Rua dos Garis" |
| `endereco` | string | Endereço/descrição | "Casa...Dos Estados, Guarapuava" |
| `quartos` | float | Número de quartos | 2.0 |
| `banheiros` | float | Número de banheiros | 2.0 |
| `area_m2` | float | Área em m² | 65.0 |
| `link` | string | URL do anúncio | "https://..." |
| `cidade` | string | Cidade | "guarapuava" |
| `estado` | string | Estado | "pr" |
| `data_coleta` | string | Data/hora da coleta | "2026-02-06 16:34:38" |

---

## 🐛 Troubleshooting

### Problema: Scraper sendo bloqueado

**Solução**: Aumentar delays
```python
DELAY_MIN = 10.0
DELAY_MAX = 20.0
```

### Problema: Arquivos não encontrados ao unir

**Solução**: Verificar caminho
```bash
ls data/raw/por_pagina/
```

### Problema: Muitas duplicatas

**Solução**: O script `unir_arquivos.py` já remove duplicatas automaticamente

---

## 📝 Próximos Passos

Após coletar e consolidar os dados:

1. **Limpeza**: Converter preços para float, padronizar endereços
2. **Feature Engineering**: Extrair bairro, calcular preço/m²
3. **Modelagem**: Treinar modelo de regressão para prever preços

---

## ✅ Checklist de Uso

- [ ] Ativar ambiente conda: `conda activate regression`
- [ ] Executar scraper: `python src/scraping/zapimoveis/venda.py`
- [ ] Informar cidade, estado e número de páginas
- [ ] Aguardar conclusão (pode levar vários minutos)
- [ ] Verificar arquivos em `data/raw/por_pagina/`
- [ ] Unir arquivos: `python data/unir_arquivos.py`
- [ ] Verificar arquivo consolidado em `data/raw/`

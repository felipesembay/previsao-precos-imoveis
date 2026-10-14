-- Tabelas do projeto de aluguel (São Paulo). Mesmo banco do projeto de compra.
-- Uso: mysql -u root -p < streamlit_app/db/conf_aluguel.sql
CREATE DATABASE IF NOT EXISTS imoveis;
USE imoveis;

CREATE TABLE IF NOT EXISTS predicoes_aluguel (
    id INT AUTO_INCREMENT PRIMARY KEY,

    endereco VARCHAR(255),
    bairro VARCHAR(120),
    latitude DECIMAL(10,7),
    longitude DECIMAL(10,7),

    tipo_imovel_cat VARCHAR(50),
    area FLOAT,
    bedrooms INT,
    bathrooms INT,
    suites INT,
    parkingSpaces INT,
    mobiliado INT DEFAULT 0,
    am_ar_condicionado INT DEFAULT 0,
    inst_piscina INT DEFAULT 0,
    inst_academia INT DEFAULT 0,
    am_varanda INT DEFAULT 0,

    aluguel_anuncio FLOAT,
    aluguel_predito FLOAT,
    pct_custo_extra FLOAT,
    custo_total_estimado FLOAT,

    erro_absoluto FLOAT,
    erro_percentual FLOAT,       -- fração (0.15 = 15%)

    modelo VARCHAR(100),
    versao_modelo VARCHAR(50),
    origem VARCHAR(20),          -- 'individual' ou 'lote'

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_aluguel_created (created_at),
    INDEX idx_aluguel_versao (modelo, versao_modelo)
);

-- Features numéricas exatamente como entraram no modelo (base para o drift)
CREATE TABLE IF NOT EXISTS features_monitoramento_aluguel (
    id INT AUTO_INCREMENT PRIMARY KEY,
    predicao_id INT,

    bedrooms FLOAT,
    bathrooms FLOAT,
    parkingSpaces FLOAT,
    area FLOAT,
    suites FLOAT,
    score_escola_privada FLOAT,
    score_escola_publica FLOAT,
    score_hospitais FLOAT,
    score_mercado FLOAT,
    score_farmacia FLOAT,
    score_parque FLOAT,
    score_seguranca FLOAT,
    score_metro FLOAT,
    mobiliado FLOAT,
    am_ar_condicionado FLOAT,
    inst_piscina FLOAT,
    inst_academia FLOAT,
    am_varanda FLOAT,
    dist_centro_km FLOAT,
    dist_polo_km FLOAT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (predicao_id) REFERENCES predicoes_aluguel(id)
);

-- Erro do modelo nas previsões com aluguel de anúncio informado
-- SELECT COUNT(*) AS total, AVG(erro_absoluto) AS mae, AVG(erro_percentual) AS mape
-- FROM predicoes_aluguel WHERE erro_percentual IS NOT NULL;

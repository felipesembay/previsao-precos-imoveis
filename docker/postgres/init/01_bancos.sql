-- Executado só na primeira inicialização do volume do Postgres.
-- O banco `imoveis` é criado pelo POSTGRES_DB; o esquema dele vem de 02_schema.sql.
CREATE DATABASE metabase;   -- banco interno do Metabase (dashboards, usuários)
CREATE DATABASE airflow;    -- reservado para o Airflow do retreino automático

# Roadmap: projetos de portfólio (MLOps e AI Engineer)

Oct 11, 2026 · @Felipe Sembay

## Específico ou generalista?

Cada projeto deve ser específico para um cargo, mas os dois devem compartilhar a mesma base técnica. Juntos, cobrem os quatro cargos analisados (Data Scientist, AI Engineer, ML Engineer e MLOps); isolados, cobririam só um ou dois.

Algumas skills aparecem em todos ou quase todos os cargos: **Python, AWS, CI/CD, SQL, Git e Docker**. LLM aparece nos quatro, inclusive em Data Scientist (128 vagas) e MLOps (32 de 57 vagas).

Isso sugere uma estratégia em forma de "T":

- **Base comum**, construída uma vez e reaproveitada: Python, SQL, Docker, CI/CD no GitHub Actions, AWS, Terraform e PostgreSQL.
- **Especialização por projeto**: o projeto 1 mostra ciclo de vida de modelo (MLOps e ML Engineer); o projeto 2 mostra LLM em produção (AI Engineer).

Três cuidados ao ler os dados:

- **Salários:** amostras pequenas (5 a 38 vagas por skill) e do mercado americano. Use como sinal de direção, não como valor esperado.
- **MLOps:** são só 57 vagas. Vale mais a proporção do que o número absoluto.
- **Lacunas da extração:** observabilidade, avaliação e agentes não aparecem em nenhum ranking, provavelmente porque o extrator não tem essas categorias. Na entrevista, esses temas costumam ser os diferenciais.

## Projeto 1: Previsão de aluguel em SP (foco MLOps)

O projeto deve priorizar CI/CD, Kubernetes e MLflow, que estão entre as skills mais frequentes nas 57 vagas de MLOps, usando ferramentas open source e infraestrutura gratuita ou de centavos.

| Skill | % das vagas de MLOps | Como entra no projeto |
| --- | --- | --- |
| CI/CD | 89% | GitHub Actions: lint, testes, treino, validação do modelo, build da imagem e deploy |
| Kubernetes | 84% | k3s numa VM gratuita (Oracle Cloud Free Tier, ARM com 4 núcleos e 24 GB) ou kind dentro do CI; deploy com Helm chart |
| AWS | 60% | S3 para dados brutos e modelos, ECR para imagens; cabe no free tier ou custa centavos |
| Docker | 56% | Imagens separadas para treino e para serving |
| LLM | 56% | Opcional: extrair atributos das descrições dos anúncios ("varanda", "aceita pet") com um LLM pequeno, como feature do modelo |
| MLflow | 51% | Rastreamento de experimentos e Model Registry (staging → production) |
| Terraform | 40% | Criar bucket S3, ECR e a VM por código |
| SQL | 33% | PostgreSQL para os anúncios tratados |

Da lista de Data Scientist, vale incluir também:

- **Airflow** (ou Prefect, mais leve) e **dbt**, que estão entre as skills mais bem pagas de DS, para orquestrar coleta, transformação e treino.
- **A/B Testing**, que lidera os salários em DS ($186k) e em ML Engineer ($265k): um deploy champion/challenger em que o modelo novo roda em paralelo e um teste estatístico decide a promoção.

Peças que completam o ciclo:

- **Validação de dados:** Pandera ou Great Expectations, para barrar dados quebrados antes do treino.
- **Monitoramento:** Evidently para drift; Prometheus e Grafana para latência e erros da API.
- **Retreino:** agendado ou disparado por drift, passando pelo registry e pelo teste A/B.

**Coleta de dados.** Scraping de portais como ZAP, VivaReal ou QuintoAndar costuma violar os termos de uso, e eles bloqueiam robôs. Para não travar, comece com um dataset público de aluguéis de SP (há alguns no Kaggle) e trate a coleta como um módulo trocável. Se for coletar, respeite o robots.txt, use baixa frequência e não republique os dados brutos.

**Ordem sugerida:**

1. Dataset → treino com MLflow
2. API FastAPI no Docker
3. CI/CD
4. Orquestração (Prefect ou Airflow)
5. Monitoramento com Evidently
6. k3s e Terraform
7. A/B champion/challenger

## Projeto 2: RAG (foco AI Engineer)

Os dados agregados de AI Engineer confirmam a análise anterior (feita para uma vaga específica) e acrescentam duas prioridades: alternar entre provedores de nuvem e usar TypeScript no frontend.

| Skill | % das vagas de AI Eng | O que muda em relação à análise anterior |
| --- | --- | --- |
| LLM / RAG | 87% / 60% | Confirmado: é o núcleo. Avaliação com RAGAS continua sendo o primeiro passo |
| Azure e AWS | 48% cada | Novidade: Azure pesa tanto quanto AWS. Um módulo único de LLM permite alternar entre OpenAI, Azure OpenAI, Bedrock e Ollama por configuração |
| CI/CD | 46% | Mais alto do que parecia. A avaliação de RAG rodando no CI, falhando se a qualidade cair, vira peça central |
| LangChain | 29%; salário mais alto ($176k) | Confirma a migração do roteamento para LangGraph |
| PostgreSQL | entre as mais bem pagas | Confirma pgvector no lugar do FAISS, com metadados, logs e feedback no mesmo banco |
| TypeScript | 3º mais bem pago ($166k) | Novidade: o frontend já é React; migrar para TypeScript custa pouco e passa a contar como skill |
| Docker | 25% | Já existe no projeto |

Ajustes de custo em relação à análise anterior:

- **Em vez de ECS Fargate**, que cobra 24 horas por dia: a mesma VM com k3s do projeto 1, ou Lambda com container, que só cobra quando é usada. O Terraform continua.
- **Langfuse self-hosted** (open source, roda em Docker) em vez de LangSmith pago.
- **Ollama com um modelo local** como opção de provedor: demonstra a abstração de provedores e zera o custo de testes.
- **Embeddings multilíngues open source** (bge-m3) rodando localmente.

A primeira tarefa continua sendo tirar a chave da OpenAI do YAML e lê-la do arquivo .env.

## Por onde começar

Primeiro, trocar a chave da OpenAI no RAG: é uma mudança pequena e destrava o projeto. Depois, partir para o projeto 1, por três motivos:

- Está onde está a lacuna (MLOps).
- Atinge o maior volume de vagas (Data Scientist, ML Engineer e MLOps).
- Monta a infraestrutura (GitHub Actions, Terraform, k3s, PostgreSQL) que o projeto 2 depois só reaproveita.

* [ ] Mover a chave da OpenAI para o .env no projeto RAG
* [ ] Projeto 1: dataset e treino com MLflow
* [ ] Projeto 1: API, CI/CD e orquestração
* [ ] Projeto 1: monitoramento, k3s, Terraform e A/B
* [ ] Projeto 2: avaliação RAGAS, LangGraph, Langfuse e pgvector

"""
Script para RETOMAR scraping do ZapImóveis
Detecta automaticamente a última página coletada e continua de lá
"""

import os
import re
import sys
from pathlib import Path

# Importar o scraper original
from src.scraping.zapimoveis.aluguel import ZapImoveisScraperRobusto, logger


def detectar_ultima_pagina_coletada(cidade: str, estado: str, diretorio: str = "data/raw/zapimoveis/por_pagina") -> int:
    """
    Detecta qual foi a última página coletada com sucesso
    
    Args:
        cidade: Nome da cidade
        estado: Sigla do estado
        diretorio: Diretório onde estão os arquivos
        
    Returns:
        Número da última página coletada (ou 0 se nenhuma)
    """
    try:
        # Verificar se o diretório existe
        path = Path(diretorio)
        if not path.exists():
            logger.warning(f"Diretório {diretorio} não existe. Começando do zero.")
            return 0
        
        # Padrão: cidade_estado_paginaN.csv
        padrao = f"{cidade}_{estado}_pagina(\\d+)\\.csv"
        
        paginas_encontradas = []
        
        # Listar todos os arquivos e extrair números de páginas
        for arquivo in path.glob(f"{cidade}_{estado}_pagina*.csv"):
            match = re.search(r'pagina(\d+)\.csv', arquivo.name)
            if match:
                numero_pagina = int(match.group(1))
                
                # Verificar se o arquivo não está vazio
                if arquivo.stat().st_size > 100:  # Pelo menos 100 bytes
                    paginas_encontradas.append(numero_pagina)
        
        if paginas_encontradas:
            ultima_pagina = max(paginas_encontradas)
            logger.info(f"✓ Última página coletada detectada: {ultima_pagina}")
            logger.info(f"✓ Total de páginas encontradas: {len(paginas_encontradas)}")
            return ultima_pagina
        else:
            logger.warning("Nenhuma página anterior encontrada. Começando do zero.")
            return 0
            
    except Exception as e:
        logger.error(f"Erro ao detectar última página: {e}")
        return 0


def retomar_scraping(
    cidade: str,
    estado: str,
    apenas_residenciais: bool = False,
    num_paginas_adicionais: int = None,
    delay_min: float = 5.0,
    delay_max: float = 10.0
):
    """
    Retoma o scraping a partir da última página coletada
    
    Args:
        cidade: Nome da cidade
        estado: Sigla do estado
        apenas_residenciais: Se True, filtra apenas imóveis residenciais
        num_paginas_adicionais: Quantas páginas coletar (None = até acabar)
        delay_min: Delay mínimo entre páginas (segundos)
        delay_max: Delay máximo entre páginas (segundos)
    """
    
    print("="*60)
    print("RETOMAR SCRAPING - ZAPIMOVEIS")
    print("="*60)
    
    # Detectar última página
    ultima_pagina = detectar_ultima_pagina_coletada(cidade, estado)
    proxima_pagina = ultima_pagina + 1
    
    print(f"\n📊 Status:")
    print(f"   Última página coletada: {ultima_pagina}")
    print(f"   Próxima página a coletar: {proxima_pagina}")
    
    if num_paginas_adicionais:
        pagina_final = proxima_pagina + num_paginas_adicionais - 1
        print(f"   Páginas a coletar: {proxima_pagina} até {pagina_final}")
    else:
        print(f"   Páginas a coletar: {proxima_pagina} até acabar")
    
    print("\n" + "="*60)
    
    confirmacao = input("\n▶️  Continuar scraping? (s/n): ").strip().lower()
    if confirmacao not in ['s', 'sim', 'y', 'yes', '']:
        print("❌ Scraping cancelado.")
        return
    
    # Criar scraper
    scraper = ZapImoveisScraperRobusto(
        cidade=cidade,
        estado=estado,
        headless=False,
        apenas_residenciais=apenas_residenciais
    )
    
    # Ajustar a base_url para começar da página correta não é necessário
    # pois o scraping_pagina_individual aceita o número da página
    
    # Realizar scraping apenas das páginas restantes
    print(f"\n🚀 Iniciando scraping da página {proxima_pagina}...\n")
    
    import random
    import time
    
    paginas_vazias_consecutivas = 0
    pagina_atual = proxima_pagina
    
    # Se num_paginas_adicionais foi especificado, calcular até onde ir
    if num_paginas_adicionais:
        pagina_maxima = proxima_pagina + num_paginas_adicionais - 1
    else:
        pagina_maxima = 9999  # Valor alto
    
    while pagina_atual <= pagina_maxima:
        try:
            # Fazer scraping da página
            imoveis_pagina = scraper.scraping_pagina_individual(pagina_atual)
            
            # Se não encontrou imóveis, pode ser que acabaram as páginas
            if len(imoveis_pagina) == 0:
                paginas_vazias_consecutivas += 1
                logger.warning(f"Página {pagina_atual} sem imóveis ({paginas_vazias_consecutivas}/2)")
                
                # Se 2 páginas consecutivas vazias, provavelmente acabou
                if paginas_vazias_consecutivas >= 2:
                    logger.info(f"Encerrando scraping: 2 páginas consecutivas sem dados")
                    break
            else:
                paginas_vazias_consecutivas = 0
                scraper.imoveis.extend(imoveis_pagina)
                
                # Salvar página individualmente
                import pandas as pd
                df_pagina = pd.DataFrame(imoveis_pagina)
                scraper._salvar_pagina_individual(df_pagina, pagina_atual)
            
            # Próxima página
            pagina_atual += 1
            
            # Delay entre páginas (exceto na última)
            if pagina_atual <= pagina_maxima:
                delay = random.uniform(delay_min, delay_max)
                logger.info(f"Aguardando {delay:.1f}s antes da próxima página...")
                time.sleep(delay)
            
        except Exception as e:
            logger.error(f"Erro ao processar página {pagina_atual}: {e}")
            pagina_atual += 1
            continue
    
    # Resumo final
    print("\n" + "="*60)
    print("SCRAPING CONCLUÍDO")
    print("="*60)
    print(f"Páginas processadas: {proxima_pagina} até {pagina_atual - 1}")
    print(f"Total de imóveis coletados nesta sessão: {len(scraper.imoveis)}")
    print("="*60)
    
    # Salvar dados consolidados desta sessão
    if scraper.imoveis:
        from datetime import datetime

        import pandas as pd
        df = pd.DataFrame(scraper.imoveis)
        caminho = f'data/raw/zapimoveis/imoveis_{cidade}_retomada_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        scraper.salvar_dados(df, caminho)


def main():
    """
    Função principal - configuração interativa
    """
    print("="*60)
    print("RETOMAR SCRAPING - CONFIGURAÇÃO")
    print("="*60)
    
    # Tentar detectar cidade e estado automaticamente dos arquivos existentes
    try:
        arquivos = list(Path("data/raw/zapimoveis/por_pagina").glob("*_pagina*.csv"))
        if arquivos:
            # Extrair cidade e estado do primeiro arquivo
            primeiro_arquivo = arquivos[0].name
            match = re.match(r'(.+?)_([a-z]{2})_pagina', primeiro_arquivo)
            if match:
                cidade_detectada = match.group(1)
                estado_detectado = match.group(2)
                print(f"\n✓ Detectado automaticamente:")
                print(f"   Cidade: {cidade_detectada}")
                print(f"   Estado: {estado_detectado}")
                
                usar_detectado = input("\n   Usar esses valores? (s/n): ").strip().lower()
                if usar_detectado in ['s', 'sim', 'y', 'yes', '']:
                    cidade = cidade_detectada
                    estado = estado_detectado
                else:
                    cidade = input("\n📍 Digite o nome da cidade: ").strip().lower()
                    estado = input("📍 Digite a sigla do estado: ").strip().lower()
            else:
                cidade = input("\n📍 Digite o nome da cidade: ").strip().lower()
                estado = input("📍 Digite a sigla do estado: ").strip().lower()
        else:
            cidade = input("\n📍 Digite o nome da cidade: ").strip().lower()
            estado = input("📍 Digite a sigla do estado: ").strip().lower()
    except:
        cidade = input("\n📍 Digite o nome da cidade: ").strip().lower()
        estado = input("📍 Digite a sigla do estado: ").strip().lower()
    
    # Tipo de imóveis
    print("\n🏘️  Tipo de imóveis coletados anteriormente:")
    print("   1. TODOS os imóveis (residenciais + comerciais)")
    print("   2. APENAS RESIDENCIAIS")
    tipo_scraping = input("   Qual foi usado? (1/2): ").strip()
    apenas_residenciais = (tipo_scraping == '2')
    
    # Número de páginas
    print("\n📄 Quantas páginas coletar:")
    print("   - Digite um número específico (ex: 50)")
    print("   - Pressione ENTER para coletar até acabar")
    num_paginas_input = input("   Sua escolha: ").strip()
    
    if num_paginas_input:
        try:
            num_paginas = int(num_paginas_input)
        except ValueError:
            print("   ⚠️  Valor inválido. Coletando até acabar.")
            num_paginas = None
    else:
        num_paginas = None
    
    # Executar retomada
    retomar_scraping(
        cidade=cidade,
        estado=estado,
        apenas_residenciais=apenas_residenciais,
        num_paginas_adicionais=num_paginas,
        delay_min=5.0,
        delay_max=10.0
    )


if __name__ == "__main__":
    main()

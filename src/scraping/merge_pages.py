"""
Script para unir todos os arquivos CSV de páginas individuais em um único DataFrame
"""

import glob
import re
from pathlib import Path

import pandas as pd


def unir_arquivos_por_cidade(cidade: str, estado: str, diretorio: str = None, excluir_paginas: list = None) -> pd.DataFrame:
    """
    Une todos os arquivos CSV de uma cidade específica
    
    Args:
        cidade: Nome da cidade
        estado: Sigla do estado
        diretorio: Diretório onde estão os arquivos (None = usar pasta por_pagina/)
        excluir_paginas: Lista de números de páginas a excluir (ex: [334, 335])
        
    Returns:
        DataFrame com todos os dados unidos
    """
    # Caminho base - usar por_pagina/ se não especificado
    if diretorio is None:
        # Diretório do script atual
        script_dir = Path(__file__).parent
        base_path = script_dir / "por_pagina"
    else:
        base_path = Path(diretorio).resolve()
    
    # Padrão de busca: cidade_estado_paginaN.csv
    pattern = f"{cidade}_{estado}_pagina*.csv"
    arquivos = sorted(base_path.glob(pattern))
    
    if not arquivos:
        print(f"⚠️  Nenhum arquivo encontrado para {cidade}/{estado}")
        print(f"   Padrão de busca: {pattern}")
        print(f"   Diretório: {base_path}")
        return pd.DataFrame()
    
    print(f"📁 Encontrados {len(arquivos)} arquivos para {cidade.title()}/{estado.upper()}")
    print(f"   Diretório: {base_path}\n")
    
    # Ler e unir todos os arquivos
    dfs = []
    excluidos = 0
    for arquivo in arquivos:
        try:
            # Extrair número da página do nome do arquivo
            match = re.search(r'pagina(\d+)', arquivo.name)
            pagina_num = int(match.group(1)) if match else 0
            
            # Verificar se a página deve ser excluída
            if excluir_paginas and pagina_num in excluir_paginas:
                print(f"   ⊘ {arquivo.name}: EXCLUÍDA (página {pagina_num})")
                excluidos += 1
                continue
            
            df = pd.read_csv(arquivo)
            
            print(f"   ✓ {arquivo.name}: {len(df)} imóveis")
            dfs.append(df)
        except Exception as e:
            print(f"   ✗ Erro ao ler {arquivo.name}: {e}")
    
    if excluidos > 0:
        print(f"\n🚫 Total de páginas excluídas: {excluidos}")
    
    if not dfs:
        return pd.DataFrame()
    
    # Concatenar todos os DataFrames
    df_completo = pd.concat(dfs, ignore_index=True)
    
    # Remover duplicatas baseado no link
    if 'link' in df_completo.columns:
        antes = len(df_completo)
        df_completo = df_completo.drop_duplicates(subset=['link'], keep='first')
        depois = len(df_completo)
        
        if antes != depois:
            print(f"\n🔄 Removidas {antes - depois} duplicatas")
    
    return df_completo


def unir_todos_arquivos(diretorio: str = None) -> pd.DataFrame:
    """
    Une TODOS os arquivos CSV do diretório, independente da cidade
    
    Args:
        diretorio: Diretório onde estão os arquivos (None = usar pasta por_pagina/)
        
    Returns:
        DataFrame com todos os dados unidos
    """
    # Caminho base - usar por_pagina/ se não especificado
    if diretorio is None:
        # Diretório do script atual
        script_dir = Path(__file__).parent
        base_path = script_dir / "por_pagina"
    else:
        base_path = Path(diretorio).resolve()
    
    # Buscar todos os arquivos CSV com padrão cidade_estado_paginaN.csv
    arquivos = sorted(base_path.glob("*_pagina*.csv"))
    
    if not arquivos:
        print(f"⚠️  Nenhum arquivo encontrado em {base_path}")
        print(f"   Padrão de busca: *_pagina*.csv")
        return pd.DataFrame()
    
    print(f"📁 Encontrados {len(arquivos)} arquivos no total")
    print(f"   Diretório: {base_path}\n")
    
    # Ler e unir todos os arquivos
    dfs = []
    for arquivo in arquivos:
        try:
            df = pd.read_csv(arquivo)
            print(f"   ✓ {arquivo.name}: {len(df)} imóveis")
            dfs.append(df)
        except Exception as e:
            print(f"   ✗ Erro ao ler {arquivo.name}: {e}")
    
    if not dfs:
        return pd.DataFrame()
    
    # Concatenar todos os DataFrames
    df_completo = pd.concat(dfs, ignore_index=True)
    
    # Remover duplicatas baseado no link
    if 'link' in df_completo.columns:
        antes = len(df_completo)
        df_completo = df_completo.drop_duplicates(subset=['link'], keep='first')
        depois = len(df_completo)
        
        if antes != depois:
            print(f"\n🔄 Removidas {antes - depois} duplicatas")
    
    return df_completo


def salvar_arquivo_unido(df: pd.DataFrame, cidade: str = None, estado: str = None):
    """
    Salva o DataFrame unido em um arquivo CSV
    
    Args:
        df: DataFrame a ser salvo
        cidade: Nome da cidade (opcional)
        estado: Sigla do estado (opcional)
    """
    if df.empty:
        print("⚠️  DataFrame vazio, nada para salvar")
        return
    
    # Salvar no diretório data/raw/zapimoveis/
    script_dir = Path(__file__).parent
    output_dir = script_dir  # Salva no mesmo diretório do script (data/raw/zapimoveis/)
    
    # Nome do arquivo
    if cidade and estado:
        nome_arquivo = f"imoveis_{cidade}_{estado}_completo.csv"
    else:
        nome_arquivo = "imoveis_todos_completo.csv"
    
    caminho = output_dir / nome_arquivo
    
    # Salvar
    df.to_csv(caminho, index=False, encoding='utf-8')
    print(f"\n✅ Arquivo salvo: {caminho}")
    print(f"   Total de imóveis: {len(df)}")


def main():
    """
    Função principal com menu interativo
    """
    print("="*60)
    print("UNIR ARQUIVOS CSV - ZAPIMOVEIS")
    print("="*60)
    
    print("\nOpções:")
    print("1. Unir arquivos de uma cidade específica")
    print("2. Unir TODOS os arquivos")
    
    opcao = input("\nEscolha uma opção (1 ou 2): ").strip()
    
    if opcao == "1":
        cidade = input("\n📍 Digite o nome da cidade: ").strip().lower()
        estado = input("📍 Digite a sigla do estado: ").strip().lower()
        
        # Perguntar sobre exclusão de páginas
        excluir = input("\n🚫 Deseja excluir páginas específicas? (s/n): ").strip().lower()
        excluir_paginas = None
        
        if excluir in ['s', 'sim', 'y', 'yes']:
            paginas_str = input("   Digite os números das páginas separados por vírgula (ex: 334,335): ").strip()
            try:
                excluir_paginas = [int(p.strip()) for p in paginas_str.split(',') if p.strip()]
                print(f"   Páginas a excluir: {excluir_paginas}")
            except ValueError:
                print("   ⚠️  Formato inválido. Nenhuma página será excluída.")
                excluir_paginas = None
        
        print(f"\n🔄 Unindo arquivos de {cidade.title()}/{estado.upper()}...")
        df = unir_arquivos_por_cidade(cidade, estado, excluir_paginas=excluir_paginas)
        
        if not df.empty:
            print("\n" + "="*60)
            print("RESUMO DOS DADOS")
            print("="*60)
            print(df.info())
            print("\nPrimeiros registros:")
            print(df.head())
            
            # Mostrar estatísticas básicas
            if 'preco' in df.columns:
                print("\n💰 Estatísticas de preço:")
                # Tentar converter preço para numérico se estiver como string
                try:
                    preco_numerico = df['preco'].str.replace('R$ ', '').str.replace('.', '').str.replace(',', '.').astype(float)
                    print(f"   Média: R$ {preco_numerico.mean():,.2f}")
                    print(f"   Mediana: R$ {preco_numerico.median():,.2f}")
                    print(f"   Mínimo: R$ {preco_numerico.min():,.2f}")
                    print(f"   Máximo: R$ {preco_numerico.max():,.2f}")
                except:
                    pass
            
            salvar_arquivo_unido(df, cidade, estado)
    
    elif opcao == "2":
        print("\n🔄 Unindo TODOS os arquivos...")
        df = unir_todos_arquivos()
        
        if not df.empty:
            print("\n" + "="*60)
            print("RESUMO DOS DADOS")
            print("="*60)
            print(df.info())
            print("\nPrimeiros registros:")
            print(df.head())
            
            # Mostrar estatísticas por cidade
            if 'cidade' in df.columns and 'estado' in df.columns:
                print("\n📊 Imóveis por cidade:")
                contagem = df.groupby(['cidade', 'estado']).size().reset_index(name='quantidade')
                print(contagem.to_string(index=False))
            
            salvar_arquivo_unido(df)
    
    else:
        print("❌ Opção inválida")


if __name__ == "__main__":
    main()

"""
Web Scraper Robusto para ZapImóveis
Evita bloqueios fechando e reabrindo o navegador entre páginas
"""

import json
import logging
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraping.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ZapImoveisScraperRobusto:
    """
    Scraper robusto para ZapImóveis
    Estratégia anti-bloqueio: fecha e reabre navegador entre páginas
    """
    
    # Lista de User-Agents para rotação
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    ]
    
    def __init__(self, cidade: str = "guarapuava", estado: str = "pr", headless: bool = False, apenas_residenciais: bool = False):
        """
        Args:
            cidade: Nome da cidade
            estado: Sigla do estado
            headless: Se True, executa sem interface gráfica
            apenas_residenciais: Se True, filtra apenas imóveis residenciais (sem comerciais)
        """
        self.cidade = cidade
        self.estado = estado
        self.headless = headless
        self.imoveis = []
        
        # Construir URL baseado no filtro
        if apenas_residenciais:
            # URL com filtros de tipos residenciais (apartamento, casa, studio, kitnet, etc)
            # Exclui salas comerciais, escritórios, lojas, etc.
            tipos = "apartamento_residencial%2Cstudio_residencial%2Ckitnet_residencial%2Ccasa_residencial%2Csobrado_residencial%2Ccondominio_residencial%2Ccasa-vila_residencial%2Ccobertura_residencial%2Cflat_residencial%2Cloft_residencial"
            self.base_url = f"https://www.zapimoveis.com.br/aluguel/apartamentos/{estado}+{cidade}/?tipos={tipos}"
        else:
            # URL padrão - todos os tipos de imóveis
            self.base_url = f"https://www.zapimoveis.com.br/aluguel/imoveis/{estado}+{cidade}/"
        
    def _obter_user_agent_aleatorio(self) -> str:
        """Retorna um User-Agent aleatório da lista"""
        return random.choice(self.USER_AGENTS)
    
    def _criar_driver(self) -> webdriver.Chrome:
        """
        Cria uma nova instância do Selenium WebDriver
        Com configurações anti-detecção
        """
        options = Options()
        
        if self.headless:
            options.add_argument('--headless')
        
        # Configurações anti-detecção
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # User-Agent aleatório
        user_agent = self._obter_user_agent_aleatorio()
        options.add_argument(f'user-agent={user_agent}')
        
        # Viewport aleatório para parecer mais humano
        width = random.randint(1366, 1920)
        height = random.randint(768, 1080)
        options.add_argument(f'--window-size={width},{height}')
        
        # Desabilitar WebRTC (pode vazar IP real)
        options.add_argument('--disable-webrtc')
        
        # Criar driver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Executar script para esconder automação
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        logger.info(f"Driver criado com User-Agent: {user_agent[:50]}...")
        return driver
    
    def _fechar_driver(self, driver: webdriver.Chrome):
        """Fecha completamente o driver"""
        try:
            driver.quit()
            logger.info("Driver fechado")
        except Exception as e:
            logger.warning(f"Erro ao fechar driver: {e}")
    
    def _simular_comportamento_humano(self, driver: webdriver.Chrome):
        """
        Simula comportamento humano com scrolls e movimentos
        """
        try:
            # Scroll gradual para baixo
            for i in range(3):
                scroll_amount = random.randint(300, 700)
                driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                time.sleep(random.uniform(0.5, 1.5))
            
            # Scroll até o final
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(1, 2))
            
            # Scroll de volta para cima um pouco
            driver.execute_script("window.scrollBy(0, -500);")
            time.sleep(random.uniform(0.5, 1))
            
        except Exception as e:
            logger.debug(f"Erro ao simular comportamento: {e}")
    
    def _detectar_total_paginas(self) -> int:
        """
        Detecta automaticamente o número total de páginas disponíveis
        """
        driver = None
        try:
            driver = self._criar_driver()
            driver.get(self.base_url)
            time.sleep(5)
            
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            
            # Procurar por elementos de paginação
            # ZapImóveis geralmente mostra "Página X de Y"
            pagination_text = soup.find_all(string=re.compile(r'de\s+\d+\s+página', re.IGNORECASE))
            
            if pagination_text:
                for text in pagination_text:
                    match = re.search(r'de\s+(\d+)\s+página', text, re.IGNORECASE)
                    if match:
                        total = int(match.group(1))
                        logger.info(f"Total de páginas detectado: {total}")
                        return total
            
            # Alternativa: procurar por botões de paginação
            pagination_buttons = soup.find_all('button', {'aria-label': re.compile(r'página\s+\d+', re.IGNORECASE)})
            if pagination_buttons:
                page_numbers = []
                for btn in pagination_buttons:
                    match = re.search(r'página\s+(\d+)', btn.get('aria-label', ''), re.IGNORECASE)
                    if match:
                        page_numbers.append(int(match.group(1)))
                if page_numbers:
                    total = max(page_numbers)
                    logger.info(f"Total de páginas detectado via botões: {total}")
                    return total
            
            # Se não conseguir detectar, retornar valor padrão
            logger.warning("Não foi possível detectar o total de páginas. Usando padrão: 10")
            return 10
            
        except Exception as e:
            logger.error(f"Erro ao detectar total de páginas: {e}")
            return 10
        finally:
            if driver:
                self._fechar_driver(driver)
    
    def _extrair_dados_pagina(self, html_content: str) -> List[Dict]:
        """
        Extrai dados dos imóveis de uma página HTML
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        imoveis_pagina = []
        
        logger.info("Analisando página HTML...")
        
        # Procurar por diferentes estruturas de cards possíveis
        # Priorizar links com /imovel/ pois são os cards completos
        cards = soup.find_all('a', {'href': re.compile(r'/imovel/.*')})
        logger.info(f"Tentativa 1 (links com /imovel/): {len(cards)} cards")
        
        if not cards:
            cards = soup.find_all('a', {'data-testid': lambda x: x and 'property-card' in x.lower() if x else False})
            logger.info(f"Tentativa 2 (data-testid=property-card): {len(cards)} cards")
        
        if not cards:
            cards = soup.find_all('div', {'class': lambda x: x and 'card' in x.lower() if x else False})
            logger.info(f"Tentativa 3 (class contendo 'card'): {len(cards)} cards")
        
        if not cards:
            cards = soup.find_all('article')
            logger.info(f"Tentativa 4 (article tags): {len(cards)} cards")
        
        for idx, card in enumerate(cards, 1):
            try:
                imovel = self._extrair_imovel_do_card(card)
                if imovel:
                    imoveis_pagina.append(imovel)
                    logger.debug(f"Card {idx}: {imovel.get('endereco', 'N/A')} - {imovel.get('preco', 'N/A')}")
            except Exception as e:
                logger.debug(f"Erro ao processar card {idx}: {e}")
                continue
        
        return imoveis_pagina
    
    def _extrair_imovel_do_card(self, card) -> Optional[Dict]:
        """
        Extrai informações de um card individual de imóvel
        """
        try:
            preco = None
            endereco = None
            rua = None
            quartos = None
            banheiros = None
            area = None
            link = None
            condominio = None
            iptu = None
            
            # ====== LINK ======
            # O card inteiro é um link
            if card.name == 'a' and card.get('href'):
                link = card.get('href')
                if not link.startswith('http'):
                    link = f"https://www.zapimoveis.com.br{link}" if link.startswith('/') else link
            
            # ====== TÍTULO (contém muitas informações) ======
            titulo = card.get('title', '')
            
            # ====== RUA ======
            # Nome da rua está em um parágrafo com data-cy="rp-cardProperty-street-txt"
            rua_elem = card.find('p', {'data-cy': 'rp-cardProperty-street-txt'})
            if rua_elem:
                rua = rua_elem.get_text(strip=True)
            elif titulo:
                # Fallback: tentar extrair do título
                # Formato: "... em Rua [Nome], [Bairro]"
                match = re.search(r'em\s+(Rua|Avenida|Av\.|R\.)\s+([^,]+)', titulo, re.IGNORECASE)
                if match:
                    rua = f"{match.group(1)} {match.group(2)}".strip()
            
            # ====== ENDEREÇO ======
            # Endereço está no h2
            endereco_elem = card.find('h2')
            if endereco_elem:
                endereco = endereco_elem.get_text(strip=True)
            elif titulo:
                # Fallback: extrair do título
                # Formato: "Casa ... em [Bairro], [Cidade]"
                match = re.search(r'em\s+(.+?)(?:,\s*[A-Z]|$)', titulo)
                if match:
                    endereco = match.group(1).strip()
            
            # ====== PREÇO ======
            # Preço aparece no texto completo do card
            texto_completo = card.get_text(separator=' ', strip=True)
            preco_match = re.search(r'R\$\s*([\d.]+(?:,\d{2})?)', texto_completo)
            if preco_match:
                preco = f"R$ {preco_match.group(1)}"
            
            # ====== CONDOMÍNIO E IPTU ======
            # Procurar por elementos com a classe text-neutral-110
            condominio_iptu_elem = card.find('p', {'class': lambda x: x and 'text-neutral-110' in x if x else False})
            if condominio_iptu_elem:
                texto_cond_iptu = condominio_iptu_elem.get_text(strip=True)
                
                # Extrair Condomínio (Cond. R$ 3.600)
                cond_match = re.search(r'Cond\.?\s*R\$\s*([\d.]+(?:,\d{2})?)', texto_cond_iptu, re.IGNORECASE)
                if cond_match:
                    condominio = f"R$ {cond_match.group(1)}"
                
                # Extrair IPTU (IPTU R$ 12.000)
                iptu_match = re.search(r'IPTU\s*R\$\s*([\d.]+(?:,\d{2})?)', texto_cond_iptu, re.IGNORECASE)
                if iptu_match:
                    iptu = f"R$ {iptu_match.group(1)}"
            
            # ====== CARACTERÍSTICAS ======
            # Extrair do título primeiro (mais confiável)
            if titulo:
                # Quartos
                quartos_match = re.search(r'(\d+)\s+quarto', titulo, re.IGNORECASE)
                if quartos_match:
                    quartos = int(quartos_match.group(1))
                
                # Banheiros
                banheiros_match = re.search(r'(\d+)\s+banheiro', titulo, re.IGNORECASE)
                if banheiros_match:
                    banheiros = int(banheiros_match.group(1))
                
                # Área
                area_match = re.search(r'(\d+)\s*m²', titulo)
                if area_match:
                    area = float(area_match.group(1))
            
            # Fallback: procurar no texto do card se não encontrou no título
            if not quartos or not banheiros or not area:
                for span in card.find_all('span'):
                    texto = span.get_text(strip=True)
                    
                    if not quartos and 'quarto' in texto.lower():
                        nums = re.findall(r'\d+', texto)
                        if nums:
                            quartos = int(nums[0])
                    
                    if not banheiros and 'banheiro' in texto.lower():
                        nums = re.findall(r'\d+', texto)
                        if nums:
                            banheiros = int(nums[0])
                    
                    if not area and ('m²' in texto or 'm2' in texto.lower()):
                        nums = re.findall(r'\d+[.,]?\d*', texto)
                        if nums:
                            area = float(nums[0].replace(',', '.'))
            
            # Verificar se temos dados mínimos válidos
            if not preco and not endereco:
                return None
            
            imovel = {
                'preco': preco,
                'condominio': condominio,
                'iptu': iptu,
                'rua': rua,
                'endereco': endereco,
                'quartos': quartos,
                'banheiros': banheiros,
                'area_m2': area,
                'link': link,
                'cidade': self.cidade,
                'estado': self.estado,
                'data_coleta': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return imovel
            
        except Exception as e:
            logger.debug(f"Erro ao extrair card: {e}")
            return None

    
    def scraping_pagina_individual(self, numero_pagina: int) -> List[Dict]:
        """
        Faz scraping de UMA página específica
        Cria e fecha o driver para essa página
        
        Args:
            numero_pagina: Número da página a fazer scraping
            
        Returns:
            Lista de imóveis extraídos
        """
        driver = None
        imoveis_pagina = []
        
        try:
            logger.info(f"{'='*60}")
            logger.info(f"PÁGINA {numero_pagina}")
            logger.info(f"{'='*60}")
            
            # Criar novo driver
            driver = self._criar_driver()
            
            # Construir URL
            # Se a base_url já tem parâmetros, usar & ao invés de ?
            separador = '&' if '?' in self.base_url else '?'
            url = f"{self.base_url}{separador}pagina={numero_pagina}"
            logger.info(f"Acessando: {url}")
            
            # Acessar página
            driver.get(url)
            
            # Aguardar carregamento inicial
            tempo_espera = random.uniform(5, 8)
            logger.info(f"Aguardando {tempo_espera:.1f}s para carregamento...")
            time.sleep(tempo_espera)
            
            # Simular comportamento humano
            self._simular_comportamento_humano(driver)
            
            # Aguardar um pouco mais
            time.sleep(random.uniform(2, 3))
            
            # Extrair HTML
            html = driver.page_source
            
            # Extrair dados
            imoveis_pagina = self._extrair_dados_pagina(html)
            
            logger.info(f"✓ Página {numero_pagina}: {len(imoveis_pagina)} imóveis extraídos")
            
        except Exception as e:
            logger.error(f"Erro ao processar página {numero_pagina}: {e}")
        
        finally:
            # SEMPRE fechar o driver
            if driver:
                self._fechar_driver(driver)
        
        return imoveis_pagina
    
    def scraping_completo(
        self, 
        num_paginas: Optional[int] = None,
        delay_min: float = 5.0,
        delay_max: float = 10.0,
        auto_detectar: bool = True,
        salvar_por_pagina: bool = True
    ) -> pd.DataFrame:
        """
        Realiza scraping de múltiplas páginas
        
        Args:
            num_paginas: Número de páginas a fazer scraping (None = auto-detectar ou até acabar)
            delay_min: Delay mínimo entre páginas (segundos)
            delay_max: Delay máximo entre páginas (segundos)
            auto_detectar: Se True, detecta automaticamente o total de páginas
            salvar_por_pagina: Se True, salva cada página em arquivo separado
            
        Returns:
            DataFrame com todos os imóveis coletados
        """
        # Detectar total de páginas se necessário
        if auto_detectar and num_paginas is None:
            num_paginas = self._detectar_total_paginas()
        elif num_paginas is None:
            num_paginas = 999  # Valor alto para continuar até não ter mais dados
        
        logger.info(f"{'='*60}")
        logger.info(f"INICIANDO SCRAPING")
        logger.info(f"Cidade: {self.cidade.title()}/{self.estado.upper()}")
        logger.info(f"Páginas: {num_paginas if num_paginas < 999 else 'Até acabar'}")
        logger.info(f"Delay entre páginas: {delay_min}-{delay_max}s")
        logger.info(f"Salvar por página: {'Sim' if salvar_por_pagina else 'Não'}")
        logger.info(f"{'='*60}")
        
        self.imoveis = []
        paginas_vazias_consecutivas = 0
        
        for pagina in range(1, num_paginas + 1):
            try:
                # Fazer scraping da página
                imoveis_pagina = self.scraping_pagina_individual(pagina)
                
                # Se não encontrou imóveis, pode ser que acabaram as páginas
                if len(imoveis_pagina) == 0:
                    paginas_vazias_consecutivas += 1
                    logger.warning(f"Página {pagina} sem imóveis ({paginas_vazias_consecutivas}/2)")
                    
                    # Se 2 páginas consecutivas vazias, provavelmente acabou
                    if paginas_vazias_consecutivas >= 2:
                        logger.info(f"Encerrando scraping: 2 páginas consecutivas sem dados")
                        break
                else:
                    paginas_vazias_consecutivas = 0
                    self.imoveis.extend(imoveis_pagina)
                    
                    # Salvar página individualmente se solicitado
                    if salvar_por_pagina and len(imoveis_pagina) > 0:
                        df_pagina = pd.DataFrame(imoveis_pagina)
                        self._salvar_pagina_individual(df_pagina, pagina)
                
                # Delay entre páginas (exceto na última)
                if pagina < num_paginas:
                    delay = random.uniform(delay_min, delay_max)
                    logger.info(f"Aguardando {delay:.1f}s antes da próxima página...")
                    time.sleep(delay)
                
            except Exception as e:
                logger.error(f"Erro ao processar página {pagina}: {e}")
                continue
        
        # Converter para DataFrame
        if self.imoveis:
            df = pd.DataFrame(self.imoveis)
            # Remover duplicatas baseado no link
            if 'link' in df.columns:
                df = df.drop_duplicates(subset=['link'], keep='first')
        else:
            df = pd.DataFrame()
        
        logger.info(f"{'='*60}")
        logger.info(f"SCRAPING CONCLUÍDO")
        logger.info(f"Total de imóveis coletados: {len(df)}")
        logger.info(f"{'='*60}")
        
        return df
    
    def _salvar_pagina_individual(self, df: pd.DataFrame, numero_pagina: int):
        """
        Salva uma página individual em CSV
        
        Args:
            df: DataFrame com os dados da página
            numero_pagina: Número da página
        """
        try:
            # Criar diretório se não existir
            Path('data/raw/zapimoveis/por_pagina').mkdir(parents=True, exist_ok=True)
            
            # Nome do arquivo: cidade_estado_paginaN.csv
            caminho = f'data/raw/zapimoveis/por_pagina/{self.cidade}_{self.estado}_pagina{numero_pagina}.csv'
            
            df.to_csv(caminho, index=False, encoding='utf-8')
            logger.info(f"✓ Página {numero_pagina} salva em {caminho}")
            
        except Exception as e:
            logger.error(f"Erro ao salvar página {numero_pagina}: {e}")
    
    def salvar_dados(self, df: pd.DataFrame, caminho: Optional[str] = None):
        """
        Salva dados em CSV
        
        Args:
            df: DataFrame com os dados
            caminho: Caminho do arquivo (None = auto-gerar)
        """
        try:
            if caminho is None:
                # Criar diretório se não existir
                Path('data/raw/zapimoveis').mkdir(parents=True, exist_ok=True)
                caminho = f'data/raw/zapimoveis/imoveis_{self.cidade}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            
            df.to_csv(caminho, index=False, encoding='utf-8')
            logger.info(f"✓ Dados salvos em {caminho}")
            
        except Exception as e:
            logger.error(f"Erro ao salvar dados: {e}")


def main():
    """
    Função principal para executar o scraping com inputs do usuário
    """
    print("="*60)
    print("WEB SCRAPER ZAPIMOVEIS - CONFIGURAÇÃO")
    print("="*60)
    
    # Input: Cidade
    cidade = input("\n📍 Digite o nome da cidade (ex: sao-paulo): ").strip().lower()
    if not cidade:
        cidade = "sao-paulo"
        print(f"   Usando padrão: {cidade}")
    
    # Input: Estado
    estado = input("📍 Digite a sigla do estado (ex: sp): ").strip().lower()
    if not estado:
        estado = "sp"
        print(f"   Usando padrão: {estado}")
    
    # Input: Tipo de scraping
    print("\n🏘️  Escolha o tipo de imóveis:")
    print("   1. Raspar TODOS os imóveis (residenciais + comerciais)")
    print("   2. Raspar APENAS RESIDENCIAIS (apartamentos, casas, studios, etc.)")
    print("      → Exclui: salas comerciais, escritórios, lojas, terrenos")
    tipo_scraping = input("   Sua escolha (1/2): ").strip()
    
    apenas_residenciais = (tipo_scraping == '2')
    
    # Input: Número de páginas
    print("\n📄 Número de páginas:")
    print("   - Digite um número específico (ex: 12)")
    print("   - Pressione ENTER para coletar até acabar")
    num_paginas_input = input("   Sua escolha: ").strip()
    
    if num_paginas_input:
        try:
            num_paginas = int(num_paginas_input)
            auto_detectar = False
        except ValueError:
            print("   ⚠️  Valor inválido. Coletando até acabar.")
            num_paginas = None
            auto_detectar = False
    else:
        num_paginas = None
        auto_detectar = False
        print("   Coletando até acabar...")
    
    # Configurações fixas
    DELAY_MIN = 5.0
    DELAY_MAX = 10.0
    HEADLESS = False
    
    print("\n" + "="*60)
    print("CONFIGURAÇÃO FINAL")
    print("="*60)
    print(f"Cidade: {cidade.title()}")
    print(f"Estado: {estado.upper()}")
    print(f"Tipo: {'Apenas Residenciais' if apenas_residenciais else 'Todos os Imóveis'}")
    print(f"Páginas: {num_paginas if num_paginas else 'Até acabar'}")
    print(f"Delay entre páginas: {DELAY_MIN}-{DELAY_MAX}s")
    print(f"Salvar por página: Sim")
    print("="*60)
    
    confirmacao = input("\n▶️  Iniciar scraping? (s/n): ").strip().lower()
    if confirmacao not in ['s', 'sim', 'y', 'yes', '']:
        print("❌ Scraping cancelado.")
        return
    
    # Criar scraper
    scraper = ZapImoveisScraperRobusto(
        cidade=cidade,
        estado=estado,
        headless=HEADLESS,
        apenas_residenciais=apenas_residenciais
    )
    
    # Realizar scraping
    df_imoveis = scraper.scraping_completo(
        num_paginas=num_paginas,
        delay_min=DELAY_MIN,
        delay_max=DELAY_MAX,
        auto_detectar=auto_detectar,
        salvar_por_pagina=True
    )
    
    # Exibir informações
    print("\n" + "="*60)
    print("RESUMO DOS DADOS COLETADOS")
    print("="*60)
    print(f"Total de imóveis: {len(df_imoveis)}")
    
    if len(df_imoveis) > 0:
        print("\nPrimeiros 5 registros:")
        print(df_imoveis.head())
        
        print("\nColunas disponíveis:")
        print(df_imoveis.columns.tolist())
        
        print("\nInformações do dataset:")
        print(df_imoveis.info())
        
        # Salvar dados consolidados
        scraper.salvar_dados(df_imoveis)
        
        print("\n✅ Arquivos salvos:")
        print(f"   - Arquivos individuais: data/raw/zapimoveis/por_pagina/{cidade}_{estado}_paginaN.csv")
        print(f"   - Arquivo consolidado: data/raw/zapimoveis/imoveis_{cidade}_*.csv")
    else:
        print("\n⚠️  Nenhum imóvel foi coletado.")
        print("Verifique:")
        print("  - Se o site está acessível")
        print("  - Se o Chrome está instalado")
        print("  - Os logs em scraping.log")


if __name__ == "__main__":
    main()

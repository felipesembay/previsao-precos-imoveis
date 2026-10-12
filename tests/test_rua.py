"""
Script de teste para verificar extração do nome da rua
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
import re

options = Options()
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

try:
    url = "https://www.zapimoveis.com.br/venda/imoveis/pr+guarapuava/?pagina=1"
    print(f"Acessando: {url}")
    driver.get(url)
    
    time.sleep(8)
    
    # Scroll
    for i in range(3):
        driver.execute_script("window.scrollBy(0, 500);")
        time.sleep(1)
    
    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')
    
    # Encontrar cards
    cards = soup.find_all('a', {'href': re.compile(r'/imovel/.*')})
    print(f"\nTotal de cards encontrados: {len(cards)}")
    
    print(f"\n{'='*80}")
    print("TESTANDO EXTRAÇÃO DE RUA - PRIMEIROS 5 CARDS")
    print(f"{'='*80}")
    
    for idx, card in enumerate(cards[:5], 1):
        print(f"\n--- CARD {idx} ---")
        
        # Título
        titulo = card.get('title', '')
        print(f"Título: {titulo[:80]}...")
        
        # Rua (método principal)
        rua_elem = card.find('p', {'data-cy': 'rp-cardProperty-street-txt'})
        rua = rua_elem.get_text(strip=True) if rua_elem else None
        
        if rua:
            print(f"✓ Rua (data-cy): {rua}")
        else:
            print(f"✗ Rua (data-cy): não encontrada")
            
            # Fallback: regex no título
            match = re.search(r'em\s+(Rua|Avenida|Av\.|R\.)\s+([^,]+)', titulo, re.IGNORECASE)
            if match:
                rua_fallback = f"{match.group(1)} {match.group(2)}".strip()
                print(f"  ⚠️  Rua (fallback): {rua_fallback}")
            else:
                print(f"  ✗ Rua (fallback): não encontrada")
        
        # Endereço (h2)
        endereco_elem = card.find('h2')
        endereco = endereco_elem.get_text(strip=True) if endereco_elem else None
        print(f"Endereço: {endereco[:60]}...")
    
    print(f"\n{'='*80}")
    print("ESTATÍSTICAS")
    print(f"{'='*80}")
    
    # Contar quantos cards têm o campo rua
    total_com_rua = 0
    for card in cards:
        rua_elem = card.find('p', {'data-cy': 'rp-cardProperty-street-txt'})
        if rua_elem:
            total_com_rua += 1
    
    print(f"Cards com campo 'rua': {total_com_rua}/{len(cards)} ({total_com_rua/len(cards)*100:.1f}%)")

finally:
    driver.quit()
    print("\n✓ Driver fechado")

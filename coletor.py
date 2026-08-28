#!/usr/bin/env python3
"""
RV Bioenergia — Coletor automático de dados de mercado
Roda todo dia útil às 08:00h (Brasília) via GitHub Actions
Fontes: GitHub Datasets (Brent), RSS (notícias),
        Notícias Agrícolas — espelho do CEPEA/ESALQ (etanol hidratado/anidro semanal SP,
        pois cepea.org.br bloqueia scraping automatizado),
        CombustívelBR — dados ANP por capital de UF (paridade etanol x gasolina)
"""

import json
import re
import unicodedata
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta

OUTPUT_FILE = "dados-mercado.json"

def fetch_url(url, timeout=15):
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; RVBioenergia/1.0)',
        'Accept': 'text/html,application/json,*/*',
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"[ERRO] {url}: {e}")
        return None

def load_existing():
    """Carrega dados existentes para usar como fallback"""
    try:
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def get_brent(existing):
    """Busca preço do Brent via GitHub Datasets (atualizado diariamente, 100% confiável)"""
    print("[BRENT] Buscando dados...")
    url = "https://raw.githubusercontent.com/datasets/oil-prices/main/data/brent-daily.csv"
    content = fetch_url(url)
    if not content:
        print("[BRENT] Falhou — mantendo último valor")
        return existing.get('brent', {"valor": 72.60, "variacao": -3.84, "data": "—"})

    lines = [l for l in content.strip().split('\n') if l and not l.startswith('Date')]
    if len(lines) < 2:
        return existing.get('brent')

    last = lines[-1].split(',')
    prev = lines[-2].split(',')
    cur = round(float(last[1]), 2)
    prv = round(float(prev[1]), 2)
    variacao = round((cur - prv) / prv * 100, 2)
    data = last[0]  # YYYY-MM-DD
    # Formatar data para DD/MM/YYYY
    try:
        dt = datetime.strptime(data, '%Y-%m-%d')
        data_fmt = dt.strftime('%d/%m/%Y')
    except Exception:
        data_fmt = data

    print(f"[BRENT] USD {cur:.2f} ({variacao:+.2f}%) — {data_fmt}")
    return {"valor": cur, "variacao": variacao, "data": data_fmt}

def get_historico_brent(existing):
    """Últimas 8 semanas do Brent via GitHub Datasets"""
    print("[BRENT HIST] Atualizando histórico...")
    url = "https://raw.githubusercontent.com/datasets/oil-prices/main/data/brent-daily.csv"
    content = fetch_url(url)
    if not content:
        return existing.get('historico_brent', [])

    lines = [l for l in content.strip().split('\n') if l and not l.startswith('Date')]
    # 1 ponto por semana, últimas 8 semanas
    selecionados = lines[-40::8][-8:]
    result = []
    for l in selecionados:
        parts = l.split(',')
        if len(parts) >= 2:
            try:
                dt = datetime.strptime(parts[0], '%Y-%m-%d')
                data = dt.strftime('%d/%m')
            except Exception:
                data = parts[0][5:]
            result.append({"data": data, "valor": round(float(parts[1]), 2)})
    print(f"[BRENT HIST] {len(result)} pontos")
    return result

CAPITAIS_UF = [
    ("AC", "Acre", "rio-branco-ac"), ("AL", "Alagoas", "maceio-al"),
    ("AP", "Amapá", "macapa-ap"), ("AM", "Amazonas", "manaus-am"),
    ("BA", "Bahia", "salvador-ba"), ("CE", "Ceará", "fortaleza-ce"),
    ("DF", "Distrito Federal", "brasilia-df"), ("ES", "Espírito Santo", "vitoria-es"),
    ("GO", "Goiás", "goiania-go"), ("MA", "Maranhão", "sao-luis-ma"),
    ("MT", "Mato Grosso", "cuiaba-mt"), ("MS", "Mato Grosso do Sul", "campo-grande-ms"),
    ("MG", "Minas Gerais", "belo-horizonte-mg"), ("PA", "Pará", "belem-pa"),
    ("PB", "Paraíba", "joao-pessoa-pb"), ("PR", "Paraná", "curitiba-pr"),
    ("PE", "Pernambuco", "recife-pe"), ("PI", "Piauí", "teresina-pi"),
    ("RJ", "Rio de Janeiro", "rio-de-janeiro-rj"), ("RN", "Rio Grande do Norte", "natal-rn"),
    ("RS", "Rio Grande do Sul", "porto-alegre-rs"), ("RO", "Rondônia", "porto-velho-ro"),
    ("RR", "Roraima", "boa-vista-rr"), ("SC", "Santa Catarina", "florianopolis-sc"),
    ("SP", "São Paulo", "sao-paulo-sp"), ("SE", "Sergipe", "aracaju-se"),
    ("TO", "Tocantins", "palmas-to"),
]

def get_paridade_capitais(existing):
    """Busca preço de etanol/gasolina e paridade nas 27 capitais das UFs.
    Fonte: CombustívelBR (combustivelbr.com.br), que processa e publica os dados
    oficiais da pesquisa semanal da ANP por município — usamos apenas as capitais,
    não a base completa de +2.700 municípios."""
    print("[PARIDADE CAPITAIS] Buscando dados por capital (ANP via CombustívelBR)...")

    padrao_gas = re.compile(r'gasolina a R\$(\d+,\d+)/litro')
    padrao_eth = re.compile(r'etanol est[áa] a R\$(\d+,\d+)/litro')
    padrao_prop = re.compile(r'propor[çc][ãa]o é (\d+)%')

    estados = []
    falhas = 0
    for uf, nome, slug in CAPITAIS_UF:
        url = f"https://combustivelbr.com.br/cidade/{slug}"
        content = fetch_url(url, timeout=15)
        if not content:
            falhas += 1
            continue
        gas = padrao_gas.search(content)
        eth = padrao_eth.search(content)
        if not gas or not eth:
            falhas += 1
            continue
        gasolina = round(float(gas.group(1).replace(',', '.')), 2)
        etanol = round(float(eth.group(1).replace(',', '.')), 2)
        estados.append({"uf": uf, "nome": nome, "etanol": etanol, "gasolina": gasolina})

    if len(estados) < 20:
        print(f"[PARIDADE CAPITAIS] Falhou em {falhas}/27 — mantendo dados anteriores")
        return existing.get('nacional', {
            "paridade": 70.0, "etanol_medio": 4.80, "gasolina_media": 6.83,
            "municipios_vantajosos": 0, "municipios_pesquisados": 27
        }), existing.get('estados', [])

    etanol_medio = round(sum(e["etanol"] for e in estados) / len(estados), 2)
    gasolina_media = round(sum(e["gasolina"] for e in estados) / len(estados), 2)
    paridade = round(etanol_medio / gasolina_media * 100, 1)
    vantajosos = sum(1 for e in estados if e["etanol"] / e["gasolina"] * 100 <= 70)

    nacional = {
        "paridade": paridade,
        "etanol_medio": etanol_medio,
        "gasolina_media": gasolina_media,
        "municipios_vantajosos": vantajosos,
        "municipios_pesquisados": len(estados)
    }
    print(f"[PARIDADE CAPITAIS] {len(estados)}/27 capitais coletadas ({falhas} falhas) | Paridade nacional: {paridade}%")
    return nacional, estados

def get_etanol_cepea(existing):
    """Busca os indicadores semanais do etanol hidratado e anidro CEPEA/ESALQ (SP).
    O site oficial cepea.org.br bloqueia scraping automatizado, então usamos o
    espelho público do Notícias Agrícolas, que replica a mesma tabela do CEPEA/ESALQ
    (Fonte: Cepea/Esalq) sem bloqueio."""
    print("[ETANOL CEPEA] Buscando via espelho Notícias Agrícolas...")

    padrao = re.compile(
        r'\d{2}\s*-\s*(\d{2}/\d{2}/\d{4})[^0-9]{1,300}?(\d+,\d+)[^0-9+\-]{1,60}?([+\-]\d+,\d+)',
        re.DOTALL
    )

    def parse_indicador(url):
        content = fetch_url(url, timeout=15)
        if not content:
            return None
        resultados = []
        for data_str, valor_str, var_str in padrao.findall(content):
            try:
                resultados.append({
                    "data": data_str,
                    "valor": round(float(valor_str.replace(',', '.')), 4),
                    "variacao": round(float(var_str.replace(',', '.')), 2)
                })
            except ValueError:
                continue
        return resultados or None

    hid = parse_indicador("https://www.noticiasagricolas.com.br/cotacoes/sucroenergetico/indicador-semanal-etanol-hidratado-cepea-esalq")
    ani = parse_indicador("https://www.noticiasagricolas.com.br/cotacoes/sucroenergetico/indicador-semanal-etanol-anidro-cepea-esalq")

    if not hid or not ani:
        print("[ETANOL CEPEA] Falhou — mantendo últimos valores")
        etanol = existing.get('etanol_paulinia', {
            "hidratado": 2.2618, "hidratado_anterior": 2.2429,
            "anidro": 2.5509, "anidro_anterior": 2.5311
        })
        return etanol, existing.get('historico_hidratado', [])

    etanol = {
        "hidratado": hid[0]["valor"],
        "hidratado_anterior": hid[1]["valor"] if len(hid) > 1 else hid[0]["valor"],
        "anidro": ani[0]["valor"],
        "anidro_anterior": ani[1]["valor"] if len(ani) > 1 else ani[0]["valor"]
    }

    # Histórico: últimas 5 semanas, ordem cronológica (para o gráfico)
    ultimas5 = list(reversed(hid[:5]))
    historico = [{"data": h["data"][:5], "valor": h["valor"]} for h in ultimas5]

    print(f"[ETANOL CEPEA] Hidratado R$ {etanol['hidratado']} ({hid[0]['variacao']:+.2f}%) | Anidro R$ {etanol['anidro']} ({ani[0]['variacao']:+.2f}%)")
    return etanol, historico

def _normalizar(txt):
    """Remove acentos e coloca em minúsculas, para comparação de palavras-chave."""
    nfkd = unicodedata.normalize('NFKD', txt)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).lower()

# Só entram notícias que toquem diretamente a atuação da RV Bioenergia (trading de
# etanol/biodiesel). Notícias de soja, milho (fora do contexto de etanol), café, boi
# etc. — comuns em portais agrícolas genéricos — são descartadas mesmo vindo da
# mesma fonte, a menos que também citem um destes termos.
PALAVRAS_RELEVANTES = [
    "etanol", "biodiesel", "b100", "b-100", "diesel", "gasolina", "anp", "cepea",
    "esalq", "renovabio", "cbio", "cbios", "brent", "petroleo", "cana-de-acucar",
    "cana", "moagem", "safra de cana", "usina", "alcool combustivel", "icms",
    "pis/cofins", "cofins", "tributacao de combustiveis", "aliquota", "subvencao",
    "plp dos combustiveis", "combustivel", "combustiveis", "biocombustivel",
    "biocombustiveis", "sucroenergetico", "hidratado", "anidro", "paridade",
    "usinas sucroalcooleiras",
]

def _relevante(titulo):
    t = _normalizar(titulo)
    return any(p in t for p in PALAVRAS_RELEVANTES)

def _traduzir_en(texto):
    """Traduz um título de notícia para inglês via API pública MyMemory (gratuita,
    sem necessidade de chave). Se a tradução falhar por qualquer motivo (rede,
    limite de uso, resposta inválida), devolve o texto original em português —
    nunca deixa o pipeline quebrar por causa da tradução."""
    try:
        q = urllib.parse.quote(texto)
        url = f"https://api.mymemory.translated.net/get?q={q}&langpair=pt|en"
        content = fetch_url(url, timeout=10)
        if not content:
            return texto
        data = json.loads(content)
        traduzido = data.get('responseData', {}).get('translatedText')
        if traduzido and len(traduzido.strip()) > 3 and "MYMEMORY WARNING" not in traduzido.upper():
            return traduzido.strip()
        return texto
    except Exception:
        return texto

def get_noticias(existing):
    """Busca notícias do setor via RSS público e mantém uma janela rolante de 7 dias:
    notícias novas são adicionadas às existentes (sem apagar o que ainda é válido),
    duplicatas são removidas e o que passou de 7 dias é descartado automaticamente.
    Filtro de relevância: só entra notícia sobre etanol/biodiesel/diesel/gasolina,
    ANP/CEPEA/ESALQ, RenovaBio/CBios, Brent/petróleo, cana-de-açúcar/safra/usina ou
    tributação de combustíveis — descarta ruído de portais agrícolas genéricos.
    Não depende de IA — é uma lógica de palavras-chave + data + deduplicação,
    mais previsível e barata."""
    print("[NOTICIAS] Buscando via RSS...")
    feeds = [
        ("https://www.noticiasagricolas.com.br/rss/etanol.rss", "Notícias Agrícolas", "Etanol"),
        ("https://www.novacana.com/feed", "NovaCana", "Etanol"),
        ("https://www.udop.com.br/rss.php", "UDOP", "Biocombustíveis"),
    ]
    novas = []
    descartadas = 0
    for url, fonte, tag_padrao in feeds:
        content = fetch_url(url, timeout=10)
        if not content:
            continue
        # Suporte a CDATA e tags diretas
        titles = re.findall(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', content)
        links = re.findall(r'<link>(?:<!\[CDATA\[)?(https?://[^<\]]+)(?:\]\]>)?</link>', content)
        for i, title in enumerate(titles[1:15]):
            title = title.strip()
            if not title or len(title) < 10:
                continue
            if not _relevante(title):
                descartadas += 1
                continue
            tag = "Etanol" if "etanol" in title.lower() else \
                  "Brent" if any(w in title.lower() for w in ["brent","petróleo","petroleo","crude"]) else \
                  "Produção" if any(w in title.lower() for w in ["safra","moagem","produção","usina"]) else \
                  "ANP" if "anp" in title.lower() else \
                  "RenovaBio" if any(w in title.lower() for w in ["cbio","renovabio","carbono"]) else \
                  tag_padrao
            novas.append({
                "titulo": title[:120],
                "fonte": fonte,
                "url": links[i+1] if i+1 < len(links) else "#",
                "tag": tag,
                "data": datetime.now().strftime("%d/%m/%Y")
            })

    if not novas:
        print("[NOTICIAS] RSS falhou ou nada relevante nesta rodada — mantendo janela de 7 dias já existente")
    print(f"[NOTICIAS] {descartadas} descartadas por não serem relevantes ao segmento")

    # Junta existentes + novas, deduplicando por URL (fallback: título) e mantendo a data mais antiga
    # de cada notícia (para a janela de 7 dias contar a partir da primeira vez que ela apareceu).
    combinadas = {}
    for n in existing.get('noticias', []) + novas:
        chave = n.get('url') if n.get('url') and n['url'] != '#' else n.get('titulo', '').lower()
        if not chave:
            continue
        if chave not in combinadas:
            combinadas[chave] = n
        else:
            # Mantém a versão com a data mais antiga (primeira coleta), mas atualiza tag/fonte se vier melhor
            existente_dt = _parse_data_br(combinadas[chave]['data'])
            nova_dt = _parse_data_br(n['data'])
            if existente_dt and nova_dt and nova_dt < existente_dt:
                combinadas[chave]['data'] = n['data']

    # Filtra: só mantém notícias com até 7 dias
    limite = datetime.now() - timedelta(days=7)
    validas = []
    for n in combinadas.values():
        dt = _parse_data_br(n['data'])
        if dt is None or dt >= limite:
            validas.append(n)

    # Traduz para inglês só as notícias que ainda não têm tradução salva
    # (as que já estão na janela de 7 dias mantêm a tradução feita anteriormente)
    traduzidas = 0
    for n in validas:
        if not n.get('titulo_en'):
            n['titulo_en'] = _traduzir_en(n['titulo'])
            traduzidas += 1
    if traduzidas:
        print(f"[NOTICIAS] {traduzidas} título(s) traduzido(s) para inglês")

    # Ordena da mais recente para a mais antiga, limita a 10 para não sobrecarregar o painel
    validas.sort(key=lambda n: _parse_data_br(n['data']) or datetime.min, reverse=True)
    resultado = validas[:10]

    print(f"[NOTICIAS] {len(novas)} relevantes coletadas | {len(resultado)} válidas na janela de 7 dias")
    return resultado

def _parse_data_br(data_str):
    """Converte 'DD/MM/YYYY' em datetime; retorna None se inválido."""
    try:
        return datetime.strptime(data_str, "%d/%m/%Y")
    except (ValueError, TypeError):
        return None

def semana_atual():
    hoje = datetime.now()
    inicio = hoje - timedelta(days=hoje.weekday())
    fim = inicio + timedelta(days=6)
    return f"{inicio.strftime('%d/%m')} – {fim.strftime('%d/%m/%Y')}"

def main():
    print("=" * 50)
    print("RV Bioenergia — Coletor de Dados")
    print(f"Executando: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 50)

    # Carrega dados existentes como fallback
    existing = load_existing()
    print(f"[INFO] Dados existentes carregados: {existing.get('atualizado','—')}")

    # Brent: 100% automático
    brent = get_brent(existing)
    hist_brent = get_historico_brent(existing)

    # Etanol CEPEA/ESALQ: automático via espelho Notícias Agrícolas
    etanol, hist_eth = get_etanol_cepea(existing)

    # Paridade e preços por estado: automático via capitais das UFs (ANP/CombustívelBR)
    nacional, estados = get_paridade_capitais(existing)

    # Notícias: RSS automático com fallback
    noticias = get_noticias(existing)

    dados = {
        "atualizado": datetime.now().isoformat(),
        "semana": semana_atual(),
        "nacional": nacional,
        "brent": brent,
        "etanol_paulinia": etanol,
        "historico_hidratado": hist_eth,
        "historico_brent": hist_brent,
        "estados": estados,
        "noticias": noticias
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    print(f"\n✓ {OUTPUT_FILE} atualizado")
    print(f"  Brent: USD {dados['brent']['valor']} ({dados['brent']['variacao']:+.2f}%)")
    print(f"  Etanol Hid.: R$ {dados['etanol_paulinia']['hidratado']}")
    print(f"  Paridade nacional: {dados['nacional']['paridade']}%")
    print(f"  Notícias: {len(dados['noticias'])}")

if __name__ == "__main__":
    main()

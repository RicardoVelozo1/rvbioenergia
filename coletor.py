#!/usr/bin/env python3
"""
RV Bioenergia — Coletor automático de dados de mercado
Roda todo dia útil às 08:00h (Brasília) via GitHub Actions
Fontes: GitHub Datasets (Brent), RSS (notícias)
Etanol/ANP: mantém últimos valores válidos se scraping falhar
"""

import json
import re
import urllib.request
import urllib.error
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

def get_noticias(existing):
    """Busca notícias do setor via RSS público"""
    print("[NOTICIAS] Buscando via RSS...")
    feeds = [
        ("https://www.noticiasagricolas.com.br/rss/etanol.rss", "Notícias Agrícolas", "Etanol"),
        ("https://www.novacana.com/feed", "NovaCana", "Etanol"),
        ("https://www.udop.com.br/rss.php", "UDOP", "Biocombustíveis"),
    ]
    noticias = []
    for url, fonte, tag_padrao in feeds:
        content = fetch_url(url, timeout=10)
        if not content:
            continue
        # Suporte a CDATA e tags diretas
        titles = re.findall(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', content)
        links = re.findall(r'<link>(?:<!\[CDATA\[)?(https?://[^<\]]+)(?:\]\]>)?</link>', content)
        for i, title in enumerate(titles[1:6]):
            title = title.strip()
            if not title or len(title) < 10:
                continue
            tag = "Etanol" if "etanol" in title.lower() else \
                  "Brent" if any(w in title.lower() for w in ["brent","petróleo","petroleo","crude"]) else \
                  "Produção" if any(w in title.lower() for w in ["safra","moagem","produção","usina"]) else \
                  "ANP" if "anp" in title.lower() else \
                  "RenovaBio" if any(w in title.lower() for w in ["cbio","renovabio","carbono"]) else \
                  tag_padrao
            noticias.append({
                "titulo": title[:120],
                "fonte": fonte,
                "url": links[i+1] if i+1 < len(links) else "#",
                "tag": tag,
                "data": datetime.now().strftime("%d/%m/%Y")
            })
        if len(noticias) >= 6:
            break

    if len(noticias) < 3:
        # Mantém notícias anteriores se RSS falhou
        print("[NOTICIAS] RSS falhou — mantendo notícias anteriores")
        return existing.get('noticias', [])

    print(f"[NOTICIAS] {len(noticias)} notícias coletadas")
    return noticias[:6]

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

    # Etanol/ANP/Estados: mantém últimos valores válidos
    # (atualizados manualmente via sessão com Claude semanalmente)
    etanol = existing.get('etanol_paulinia', {
        "hidratado": 2.2618, "hidratado_anterior": 2.2429,
        "anidro": 2.5509, "anidro_anterior": 2.5311
    })
    hist_eth = existing.get('historico_hidratado', [])
    nacional = existing.get('nacional', {
        "paridade": 63.7, "etanol_medio": 4.32,
        "gasolina_media": 6.64, "municipios_vantajosos": 257,
        "municipios_pesquisados": 387
    })
    estados = existing.get('estados', [])

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

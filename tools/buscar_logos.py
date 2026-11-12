import os, re, json, time, hashlib, urllib.parse
import requests
from bs4 import BeautifulSoup

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36',
      'Accept-Language': 'pt-BR,pt;q=0.9'}
EMP = {
 'usinas': ['Lasa Lago Azul','Bevap','Santa Helena','Laguna','Canex','Grupo Colorado','Veredas','Da Mata','Água Bonita','Alta Mogiana','Grupo Moreno','Neomile','Atena','Renuka','Tereos','Vale do Verdão','Inpasa','COFCO','Fátima do Sul','Cargill'],
 'distribuidoras': ['Ale Combustíveis','Ipiranga','Vibra Energia','Petrotorque','Montepetro','Dislub','Potencial Petróleo','Ruff','SP Combustíveis','Soll Distribuidora','Hora Combustíveis','Atem Distribuidora','Rio Branco Petróleo','Setta Combustíveis','Petroluz','Ciapetro','Larco Petróleo'],
}
SEED = {'Tereos':['tereos.com'],'COFCO':['cofcointernational.com'],'Inpasa':['inpasa.com.br'],'Vibra Energia':['vibraenergia.com.br'],
        'Ipiranga':['ipiranga.com.br'],'Ale Combustíveis':['ale.com.br'],'Cargill':['cargill.com.br'],'Renuka':['renukadobrasil.com.br']}
BAD = ('facebook','instagram','linkedin','youtube','twitter','x.com','wikipedia','cnpj','econodata','reclameaqui','google','bing','duckduckgo','glassdoor',
       'indeed','jusbrasil','casadosdados','solutudo','telelistas','apontador','guiamais','pinterest','mapquest','tiktok','whatsapp','gov.br','anp.gov','scribd','issuu','yelp','tripadvisor','cnpj.biz','empresaqui','infojobs','vagas','catho','novacana','canaonline','udop','biodieselbr','linkedin')
os.makedirs('candidatos', exist_ok=True)

def slug(s): return re.sub(r'[^a-z0-9]+','-',s.lower().encode('ascii','ignore').decode() or s.lower()).strip('-')

def search_domains(q):
    out=[]
    for url in ('https://html.duckduckgo.com/html/?q=%s'%urllib.parse.quote(q), 'https://www.bing.com/search?q=%s&setlang=pt-BR'%urllib.parse.quote(q)):
        try:
            r=requests.get(url,headers=UA,timeout=25)
            soup=BeautifulSoup(r.text,'html.parser')
            for a in soup.find_all('a',href=True):
                h=a['href']
                if 'uddg=' in h: h=urllib.parse.unquote(h.split('uddg=')[1].split('&')[0])
                if not h.startswith('http'): continue
                d=urllib.parse.urlparse(h).netloc.lower().replace('www.','')
                if d and not any(b in d for b in BAD) and d not in out: out.append(d)
            if len(out)>=3: break
        except Exception as e:
            print('  busca falhou',url[:30],e)
    return out[:4]

def candidates(domain):
    urls=[]; base='https://'+domain
    try:
        r=requests.get(base,headers=UA,timeout=25,allow_redirects=True); r.raise_for_status()
        soup=BeautifulSoup(r.text,'html.parser'); b=r.url; title=(soup.title.string or '').strip() if soup.title else ''
    except Exception as e:
        return [],'ERRO '+str(e)[:80]
    def add(u,tag):
        if not u or u.startswith('data:'): return
        u=urllib.parse.urljoin(b,u.strip())
        if u not in [x[0] for x in urls]: urls.append((u,tag))
    for img in soup.find_all('img'):
        blob=' '.join([img.get('src','') or '',img.get('alt','') or '',' '.join(img.get('class',[])),img.get('id','') or '', img.get('data-src','') or ''])
        if 'logo' in blob.lower() or 'marca' in blob.lower():
            add(img.get('src') or img.get('data-src'),'img-logo')
    for l in soup.find_all('link',rel=True):
        rel=' '.join(l['rel']).lower()
        if 'apple-touch-icon' in rel or rel=='icon' or 'shortcut' in rel: add(l.get('href'),'icon')
    for m in soup.find_all('meta'):
        if m.get('property') in ('og:image','og:logo') or m.get('name') in ('twitter:image',): add(m.get('content'),'og')
    return urls[:7],title

def wiki(q):
    out=[]
    try:
        r=requests.get('https://pt.wikipedia.org/w/api.php',params={'action':'query','generator':'search','gsrsearch':q,'gsrlimit':2,'prop':'pageimages','piprop':'original','format':'json'},headers=UA,timeout=25).json()
        for p in (r.get('query',{}).get('pages',{}) or {}).values():
            o=p.get('original',{}).get('source')
            if o: out.append((o,'wiki:'+p.get('title','')))
    except Exception as e: print('  wiki falhou',e)
    return out

index={}
for grupo,lst in EMP.items():
    for nome in lst:
        s=slug(nome); d=f'candidatos/{s}'; os.makedirs(d,exist_ok=True)
        q=nome+(' usina etanol açúcar site oficial' if grupo=='usinas' else ' distribuidora combustíveis site oficial')
        doms=SEED.get(nome,[])+[x for x in search_domains(q) if x not in SEED.get(nome,[])]
        print('==',nome,doms,flush=True)
        reg={'grupo':grupo,'nome':nome,'dominios':doms[:4],'arquivos':[]}
        n=0
        todos=[]
        for dom in doms[:3]:
            cs,title=candidates(dom)
            reg.setdefault('titulos',{})[dom]=title
            todos+= [(u,t,dom) for u,t in cs]
        todos+=[(u,t,'wikipedia') for u,t in wiki(nome+(' usina' if grupo=='usinas' else ' distribuidora'))]
        for u,t,dom in todos:
            if n>=9: break
            try:
                r=requests.get(u,headers=UA,timeout=25)
                ct=r.headers.get('content-type','').split(';')[0]
                if r.status_code!=200 or len(r.content)<300 or len(r.content)>3_000_000: continue
                ext={'image/png':'png','image/jpeg':'jpg','image/svg+xml':'svg','image/webp':'webp','image/gif':'gif','image/x-icon':'ico','image/vnd.microsoft.icon':'ico'}.get(ct)
                if not ext: continue
                fn=f'{n:02d}.{ext}'; open(f'{d}/{fn}','wb').write(r.content)
                reg['arquivos'].append({'arquivo':fn,'url':u,'tipo':t,'dominio':dom}); n+=1
            except Exception as e: pass
        index[s]=reg; time.sleep(1)
json.dump(index,open('candidatos/index.json','w'),ensure_ascii=False,indent=1)
print('FIM',sum(len(v['arquivos']) for v in index.values()),'arquivos')

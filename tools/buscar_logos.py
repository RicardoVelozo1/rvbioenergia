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
OUT=os.environ.get('OUT','candidatos')
SUBSET=[x for x in os.environ.get('SUBSET','').split('|') if x]
os.makedirs(OUT, exist_ok=True)

def slug(s): return re.sub(r'[^a-z0-9]+','-',s.lower().encode('ascii','ignore').decode() or s.lower()).strip('-')

def search_domains(q):
    out=[]
    for url in ('https://www.mojeek.com/search?q=%s'%urllib.parse.quote(q),'https://search.brave.com/search?q=%s'%urllib.parse.quote(q),'https://html.duckduckgo.com/html/?q=%s'%urllib.parse.quote(q), 'https://www.bing.com/search?q=%s&setlang=pt-BR'%urllib.parse.quote(q)):
        try:
            r=requests.get(url,headers=UA,timeout=25)
            print('  busca',url.split('/')[2],r.status_code,len(r.text))
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
    for m in re.finditer(r'["\'(=\s]([^"\'()\s<>]*(?:logo|marca|brand)[^"\'()\s<>]*\.(?:png|svg|webp|jpg|jpeg))',r.text,re.I):
        add(m.group(1).replace('\\/','/'),'regex-logo')
    return urls[:16],title

NOVA={'Lasa Lago Azul':['lago-azul','linhares-agroindustral---lasa'],'Bevap':['bevap'],'Santa Helena':['santa-helena','santa-helena-2','santa-helena-3'],'Laguna':['laguna'],'Canex':['canex'],
 'Grupo Colorado':['colorado'],'Veredas':['veredas'],'Da Mata':['da-mata'],'Água Bonita':['agua-bonita'],'Alta Mogiana':['alta-mogiana'],'Grupo Moreno':['moreno'],
 'Neomile':['neomille','neomille-maracaju'],'Atena':['atena'],'Renuka':['madhu','revati'],'Vale do Verdão':['vale-do-verdao-matriz'],'Fátima do Sul':['fatima-do-sul']}
def novacana(nome):
    doms=[];cands=[]
    for sl in NOVA.get(nome,[]):
        try:
            r=requests.get('https://www.novacana.com/usinas/'+sl,headers=UA,timeout=25)
            soup=BeautifulSoup(r.text,'html.parser')
            for a in soup.find_all('a',href=True):
                h=a['href']
                if h.startswith('http'):
                    d=urllib.parse.urlparse(h).netloc.lower().replace('www.','')
                    if d and not any(b in d for b in BAD) and 'novacana' not in d and d not in doms: doms.append(d)
            for img in soup.find_all('img'):
                blob=((img.get('src') or '')+(img.get('alt') or '')).lower()
                if 'usina' in blob or 'logo' in blob:
                    u=urllib.parse.urljoin(r.url,img.get('src') or '')
                    if 'novacana' in u: cands.append((u,'novacana:'+sl))
            print('  novacana',sl,r.status_code,doms[:4],len(cands),flush=True)
        except Exception as e: print('  novacana falhou',sl,e)
    return doms[:3],cands[:4]


from concurrent.futures import ThreadPoolExecutor
KEY={'Lasa Lago Azul':['lasa','lagoazul'],'Bevap':['bevap'],'Santa Helena':['santahelena'],'Laguna':['laguna'],'Canex':['canex'],'Grupo Colorado':['colorado'],'Veredas':['veredas'],
 'Da Mata':['damata'],'Água Bonita':['aguabonita'],'Alta Mogiana':['altamogiana'],'Grupo Moreno':['moreno'],'Neomile':['neomille','neomile'],'Atena':['atena'],'Renuka':['renuka'],
 'Tereos':['tereos'],'Vale do Verdão':['valedoverdao'],'Inpasa':['inpasa'],'COFCO':['cofco'],'Fátima do Sul':['fatimadosul','fatima'],'Cargill':['cargill'],
 'Ale Combustíveis':['alecombustiveis','ale'],'Ipiranga':['ipiranga'],'Vibra Energia':['vibraenergia','vibra'],'Petrotorque':['petrotorque'],'Montepetro':['montepetro'],'Dislub':['dislub'],
 'Potencial Petróleo':['potencial','potencialpetroleo'],'Ruff':['ruff'],'SP Combustíveis':['spcombustiveis'],'Soll Distribuidora':['soll','solldistribuidora'],'Hora Combustíveis':['hora','horacombustiveis'],
 'Atem Distribuidora':['atem','atems'],'Rio Branco Petróleo':['riobranco','riobrancopetroleo'],'Setta Combustíveis':['setta','settacombustiveis'],'Petroluz':['petroluz'],'Ciapetro':['ciapetro'],'Larco Petróleo':['larco','larcopetroleo']}
WORDS=('etanol','açúcar','acucar','álcool','alcool','usina','bioenergia','combust','petróleo','petroleo','distribuidora','energia','agro','lubrific','posto')
def guess_domains(nome):
    ks=KEY[nome]; cand=[]
    suf=['','bioenergia','energia','petroleo','combustiveis','distribuidora','agro','agroenergia','acucar','alcool','agroindustrial','sa']
    pre=['','usina','grupo']
    for k in ks:
        for p in pre:
            for sf in suf:
                for tld in ('.com.br','.com'):
                    d=p+k+sf+tld
                    if d not in cand: cand.append(d)
    def test(d):
        for scheme in ('https://','http://'):
            try:
                r=requests.get(scheme+d,headers=UA,timeout=7,allow_redirects=True)
                if r.status_code!=200: continue
                t=r.text.lower()[:200000]
                if any(k in t for k in ks) and any(w in t for w in WORDS):
                    soup=BeautifulSoup(r.text,'html.parser'); title=(soup.title.string or '').strip()[:90] if soup.title else ''
                    return (d,title,len(r.text))
            except Exception: pass
        return None
    with ThreadPoolExecutor(40) as ex: res=[x for x in ex.map(test,cand) if x]
    return res

FORCE={'Lasa Lago Azul':['lasa.com.br','lasabioenergia.com.br','usinalasa.com.br'],'Neomile':['neomille.com.br','neomille.com'],'Vale do Verdão':['valedoverdao.com.br','usinavaledoverdao.com.br','valedoverdao.com'],
 'Veredas':['usinaveredas.com.br','veredasbioenergia.com.br','veredas.agr.br'],'Renuka':['renukadobrasil.com.br','renukasugars.com'],'COFCO':['cofcointernational.com','cofco.com.br','cofcointernational.com.br'],
 'Cargill':['cargill.com.br','cargill.com'],'Ipiranga':['ipiranga.com.br','www.ipiranga.com.br','ipirangacombustiveis.com.br'],'Fátima do Sul':['fatimaagroenergetica.com.br','usinafatimadosul.com.br','fsae.com.br'],
 'Santa Helena':['gruposantahelena.com.br','usinasantahelena.com.br','energeticasantahelena.com.br'],'Soll Distribuidora':['solldistribuidora.com.br','soll.com.br','sollpetroleo.com.br','sollcombustiveis.com.br'],
 'Hora Combustíveis':['horadistribuidora.com.br'],'Vibra Energia':['vibraenergia.com.br'],'Dislub':['dislubenergia.com.br'],'Potencial Petróleo':['potencialcombustiveis.com.br'],'Bevap':['bevap.com.br'],'Canex':['canex.com.br'],
 'Grupo Colorado':['colorado.com.br','coloradodistribuidora.com.br'],'Atena':['usinaatena.com.br','atenaagro.com'],'Água Bonita':['aguabonita.com.br']}
def commons(q):
    out=[]
    try:
        r=requests.get('https://commons.wikimedia.org/w/api.php',params={'action':'query','generator':'search','gsrsearch':q+' logo','gsrnamespace':6,'gsrlimit':6,'prop':'imageinfo','iiprop':'url|mime','format':'json'},headers=UA,timeout=25).json()
        for p in (r.get('query',{}).get('pages',{}) or {}).values():
            ii=(p.get('imageinfo') or [{}])[0]; t=p.get('title','')
            if ii.get('url') and 'logo' in t.lower() and ii.get('mime','').startswith('image/'): out.append((ii['url'],'commons:'+t))
    except Exception as e: print('  commons falhou',e)
    return out[:5]

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
        s=slug(nome); d=f'{OUT}/{s}'; os.makedirs(d,exist_ok=True)
        q=nome+(' usina etanol açúcar site oficial' if grupo=='usinas' else ' distribuidora combustíveis site oficial')
        nd,nc=novacana(nome) if grupo=='usinas' else ([],[])
        if SUBSET and nome not in SUBSET: continue
        if nome in FORCE: gd=[(x,'forçado',0) for x in FORCE[nome]]
        else: gd=guess_domains(nome)
        print('  verificados:',gd,flush=True)
        doms=[x[0] for x in gd]
        print('==',nome,doms,flush=True)
        reg={'grupo':grupo,'nome':nome,'dominios':doms[:4],'verificados':gd,'arquivos':[]}
        n=0
        todos=[]
        for dom in doms[:4]:
            cs,title=candidates(dom)
            reg.setdefault('titulos',{})[dom]=title
            todos+= [(u,t,dom) for u,t in cs]
        todos+=[(u,t,'commons') for u,t in commons(nome)]
        todos+=[(u,t,'wikipedia') for u,t in wiki(nome+(' usina' if grupo=='usinas' else ' distribuidora'))]
        for u,t,dom in todos:
            if n>=22: break
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
json.dump(index,open(OUT+'/index.json','w'),ensure_ascii=False,indent=1)
print('FIM',sum(len(v['arquivos']) for v in index.values()),'arquivos')

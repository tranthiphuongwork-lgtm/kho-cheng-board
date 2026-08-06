# -*- coding: utf-8 -*-
"""Dump TOAN BO danh muc san pham tu Lark Base (bang San pham) ra JSON cho tao_tem_kien.html.
Moi item: {t: ten, g: GSKU, s: sku ngan, qc: 'N don_vi/thung', en: ten tieng anh}.
Chay tren GitHub Actions. Secret: LARK_APP_ID, LARK_APP_SECRET, LARK_APP_TOKEN.
"""
import os, json, re, urllib.request
H='https://open.larksuite.com'
APP=os.environ['LARK_APP_ID']; SEC=os.environ['LARK_APP_SECRET']; BASE=os.environ['LARK_APP_TOKEN']
T_SP='tbl7PSQh3Lq5Tlxy'

def tok():
    r=urllib.request.Request(H+'/open-apis/auth/v3/tenant_access_token/internal',
        data=json.dumps({'app_id':APP,'app_secret':SEC}).encode(),
        headers={'Content-Type':'application/json'},method='POST')
    return json.load(urllib.request.urlopen(r,timeout=30))['tenant_access_token']

def gt(v):
    while isinstance(v,dict): v=v.get('value') if 'value' in v else (v.get('text') or '')
    if isinstance(v,list): v=''.join(str(x.get('text') or x.get('name') or '') if isinstance(x,dict) else str(x) for x in v)
    return str(v or '').strip()

def fv(v):
    if isinstance(v,dict) and 'value' in v:
        x=v['value']; v=x[0] if isinstance(x,list) and x else 0
    if isinstance(v,list): v=v[0] if v else 0
    try: return float(str(v).replace(',',''))
    except: return 0.0

def fields(t):
    r=urllib.request.Request(H+f'/open-apis/bitable/v1/apps/{BASE}/tables/{T_SP}/fields?page_size=200',
        headers={'Authorization':'Bearer '+t})
    return [it['field_name'] for it in json.load(urllib.request.urlopen(r,timeout=30))['data']['items']]

def search(t,flds):
    out=[]; pt=None
    while True:
        url=f'/open-apis/bitable/v1/apps/{BASE}/tables/{T_SP}/records/search?page_size=500'+(('&page_token='+pt) if pt else '')
        r=urllib.request.Request(H+url,data=json.dumps({'field_names':flds}).encode(),
            headers={'Authorization':'Bearer '+t,'Content-Type':'application/json'},method='POST')
        d=json.load(urllib.request.urlopen(r,timeout=60))['data']
        out+=d.get('items',[])
        if d.get('has_more'): pt=d['page_token']
        else: break
    return out

UNIT=re.compile(r'\(([^)]+)\)\s*$')
def unit_of(name):
    m=UNIT.search(name or ''); 
    return m.group(1).strip() if m else ''

def main():
    t=tok()
    allf=fields(t)
    # phat hien field SKU ngan / ten tieng anh neu co
    skuf=next((f for f in allf if re.search(r'sku',f,re.I) and 'g sku' not in f.lower()), None)
    enf =next((f for f in allf if re.search(r'anh|english|\ben\b',f,re.I)), None)
    want=['G SKU','Tên sản phẩm','Phân loại','Quy cách']
    if skuf: want.append(skuf)
    if enf: want.append(enf)
    print('[debug] Fields T_SP:',allf)
    print('[debug] Dung SKU field:',skuf,'| EN field:',enf)
    items=search(t,want)
    cat=[]
    for it in items:
        f=it['fields']
        g=gt(f.get('G SKU')); nm=gt(f.get('Tên sản phẩm'))
        if not nm or not g: continue
        qcn=fv(f.get('Quy cách')); u=unit_of(nm)
        if qcn>0: qc=('%d %s/thùng'%(int(qcn),u)) if u else ('%d/thùng'%int(qcn))
        else: qc=''
        s=gt(f.get(skuf)) if skuf else ''
        en=gt(f.get(enf)) if enf else ''
        cat.append({'t':nm,'g':g,'s':s,'qc':qc,'en':en,'pl':gt(f.get('Phân loại'))})
    # sap xep theo phan loai roi ten
    cat.sort(key=lambda x:(x['pl'],x['t']))
    # bo field pl khoi output cuoi (chi de sap xep)
    out=[{'t':c['t'],'g':c['g'],'s':c['s'],'qc':c['qc'],'en':c['en']} for c in cat]
    print('[debug] Tong san pham co GSKU:',len(out))
    print('===CATALOG_JSON_START===')
    print(json.dumps(out,ensure_ascii=False,separators=(',',':')))
    print('===CATALOG_JSON_END===')

if __name__=='__main__':
    main()

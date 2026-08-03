# -*- coding: utf-8 -*-
"""Đồng bộ view 'Mua hàng' (Lark Base) -> tab lưới 'Lịch sử nhập hàng' trong Lark Sheet.
Dùng bởi bot khi nhận lệnh 'Đồng bộ mua hàng'. Ghi theo TÊN HEADER, giữ nguyên công thức.
YÊU CẦU app có scope sheets:spreadsheet + được share Editor vào Sheet."""
import json, re, datetime, urllib.request, urllib.error
import config as C

SRC_TABLE = C.T_MH                                   # tblsSoY9HERffH6A
SRC_VIEW  = 'vew3AfAswZ'
SHEET_TOKEN = 'SPOEssCrjhROBDtn9YHlrQIWgtb'
SHEET_TAB_TITLE = 'Lịch sử nhập hàng'
VN = datetime.timezone(datetime.timedelta(hours=7))

HEADER2FIELD = {
 'mã đơn':'Số ĐH','số đh':'Số ĐH','số đơn':'Số ĐH','ma don':'Số ĐH',
 'ngày':'Ngày',
 'tên sản phẩm':'Tên SP','tên sp':'Tên SP','ten san pham':'Tên SP',
 'số lượng':'Số nhập','số nhập':'Số nhập','sl':'Số nhập','so luong':'Số nhập',
 'minh chứng':'Minh chứng','ghi chú':'Ghi chú',
}
def _norm(s): return re.sub(r'\s+',' ',(s or '').strip()).lower()

def _api(t, method, path, body=None):
    data=json.dumps(body).encode() if body is not None else None
    r=urllib.request.Request(C.HOST+path, data=data,
        headers={'Authorization':'Bearer '+t,'Content-Type':'application/json'}, method=method)
    try: return json.load(urllib.request.urlopen(r, timeout=60))
    except urllib.error.HTTPError as e: return {'_http': e.code, 'body': e.read().decode()[:300]}

def _cell(v):
    if v is None: return ''
    if isinstance(v, dict):
        if 'value' in v:
            x=v['value']; return (x[0] if isinstance(x,list) and x else ('' if isinstance(x,list) else x))
        return v.get('text') or v.get('name') or ''
    if isinstance(v, list):
        p=[(x.get('text') or x.get('name') or x.get('value') or '') if isinstance(x,dict) else str(x) for x in v]
        return ' ; '.join(str(z) for z in p if z!='')
    return v

def _date(ms):
    try: return datetime.datetime.fromtimestamp(float(ms)/1000, tz=VN).strftime('%d/%m/%Y')
    except Exception: return ''

def _fv(f, name):
    if name=='Ngày': return _date(f.get('Ngày')) if f.get('Ngày') else ''
    return _cell(f.get(name))

def _col(n):
    s=''
    while n>0: n,r=divmod(n-1,26); s=chr(65+r)+s
    return s

def _read_view(t):
    out=[]; pt=None
    fields=['Số ĐH','Ngày','Tên SP','Số nhập','Minh chứng','Ghi chú']
    while True:
        p=f'/open-apis/bitable/v1/apps/{C.BASE}/tables/{SRC_TABLE}/records/search?page_size=500'+(('&page_token='+pt) if pt else '')
        d=_api(t,'POST',p,{'view_id':SRC_VIEW,'field_names':fields})
        if d.get('_http'): raise RuntimeError('Đọc Base lỗi: %s'%d.get('body'))
        d=d['data']; out+=d.get('items',[])
        if d.get('has_more'): pt=d['page_token']
        else: break
    return out

def run_sync(t):
    """t = tenant token. Trả về số dòng đã ghi."""
    items=_read_view(t)
    meta=_api(t,'GET',f'/open-apis/sheets/v2/spreadsheets/{SHEET_TOKEN}/metainfo')
    if meta.get('_http'): raise RuntimeError('Không đọc được Sheet (scope/share?): %s'%meta.get('body'))
    tab=None
    for s in meta.get('data',{}).get('sheets',[]):
        if _norm(s.get('title'))==_norm(SHEET_TAB_TITLE): tab=s.get('sheetId'); break
    if not tab: raise RuntimeError('Không thấy tab "%s".'%SHEET_TAB_TITLE)
    hd=_api(t,'GET',f'/open-apis/sheets/v2/spreadsheets/{SHEET_TOKEN}/values/{tab}!A1:AZ1')
    headers=(hd.get('data',{}).get('valueRange',{}).get('values',[]) or [[]])[0]
    colmap=[]
    for i,h in enumerate(headers, start=1):
        fld=HEADER2FIELD.get(_norm(h))
        if fld: colmap.append((_col(i), fld))
    if not colmap: raise RuntimeError('Không map được cột nào. Header: %s'%headers)
    n=len(items)
    ranges=[{'range':f'{tab}!{col}2:{col}{n+1}','values':[[_fv(it['fields'],fld)] for it in items]} for col,fld in colmap]
    w=_api(t,'POST',f'/open-apis/sheets/v2/spreadsheets/{SHEET_TOKEN}/values_batch_update',{'valueRanges':ranges})
    if w.get('_http'): raise RuntimeError('Ghi Sheet lỗi: %s'%w.get('body'))
    # xoá dư ở các cột đã map
    fc=colmap[0][0]
    dA=_api(t,'GET',f'/open-apis/sheets/v2/spreadsheets/{SHEET_TOKEN}/values/{tab}!{fc}1:{fc}100000')
    va=dA.get('data',{}).get('valueRange',{}).get('values',[]) or []
    prev=0
    for i,r in enumerate(va):
        if r and str(r[0]).strip(): prev=i+1
    if prev>n+1:
        clr=[{'range':f'{tab}!{col}{n+2}:{col}{prev}','values':[['']]*(prev-(n+1))} for col,_ in colmap]
        _api(t,'POST',f'/open-apis/sheets/v2/spreadsheets/{SHEET_TOKEN}/values_batch_update',{'valueRanges':clr})
    return n

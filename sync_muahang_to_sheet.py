# -*- coding: utf-8 -*-
"""
Đồng bộ (mirror) VIEW Lark Base -> 1 tab LƯỚI có sẵn trong Lark Sheet.
Ghi vào ĐÚNG các cột theo TÊN HEADER ở hàng 1 của tab đích; chỉ ghi cột dữ liệu,
KHÔNG đụng các cột công thức khác. Dữ liệu bắt đầu từ hàng 2.

Nguồn : Base kế toán, bảng "Mua hàng", view vew3AfAswZ.
Đích  : Lark Sheet SPOEss..., tab "Lịch sử nhập hàng".
Map   : (header đích -> field nguồn)
        Mã đơn/Số ĐH -> Số ĐH · Ngày -> Ngày · Tên sản phẩm/Tên SP -> Tên SP
        Số lượng/Số nhập -> Số nhập · Minh chứng -> Minh chứng · Ghi chú -> Ghi chú

Chạy khi bấm (workflow_dispatch). Secret: LARK_APP_ID, LARK_APP_SECRET, LARK_APP_TOKEN.
Cần: scope sheets:spreadsheet + app share Editor vào Sheet.  DRY_RUN=1 = chỉ đọc.
"""
import os, json, re, datetime, urllib.request, urllib.error

H='https://open.larksuite.com'
APP=os.environ['LARK_APP_ID']; SEC=os.environ['LARK_APP_SECRET']; BASE=os.environ['LARK_APP_TOKEN']
SRC_TABLE='tblsSoY9HERffH6A'; SRC_VIEW='vew3AfAswZ'
SHEET_TOKEN=os.environ.get('SHEET_TOKEN','SPOEssCrjhROBDtn9YHlrQIWgtb')
SHEET_TAB_TITLE=os.environ.get('SHEET_TAB_TITLE','Lịch sử nhập hàng')
DRY_RUN=(os.getenv('DRY_RUN') or '').strip() in ('1','true','yes')
VN=datetime.timezone(datetime.timedelta(hours=7))

# header (chuẩn hoá) -> tên field trong Base
HEADER2FIELD={
 'mã đơn':'Số ĐH','số đh':'Số ĐH','số đơn':'Số ĐH','ma don':'Số ĐH',
 'ngày':'Ngày',
 'tên sản phẩm':'Tên SP','tên sp':'Tên SP','ten san pham':'Tên SP',
 'số lượng':'Số nhập','số nhập':'Số nhập','sl':'Số nhập','so luong':'Số nhập',
 'minh chứng':'Minh chứng',
 'ghi chú':'Ghi chú',
}
def norm(s): return re.sub(r'\s+',' ',(s or '').strip()).lower()


def tok():
    r=urllib.request.Request(H+'/open-apis/auth/v3/tenant_access_token/internal',
        data=json.dumps({'app_id':APP,'app_secret':SEC}).encode(),
        headers={'Content-Type':'application/json'},method='POST')
    return json.load(urllib.request.urlopen(r,timeout=30))['tenant_access_token']

def api(t, method, path, body=None):
    data=json.dumps(body).encode() if body is not None else None
    r=urllib.request.Request(H+path, data=data,
        headers={'Authorization':'Bearer '+t,'Content-Type':'application/json'}, method=method)
    try: return json.load(urllib.request.urlopen(r, timeout=60))
    except urllib.error.HTTPError as e: return {'_http': e.code, 'body': e.read().decode()[:400]}

def cell(v):
    if v is None: return ''
    if isinstance(v, dict):
        if 'value' in v:
            x=v['value']; x=x[0] if isinstance(x,list) and x else (x if not isinstance(x,list) else '')
            return x
        return v.get('text') or v.get('name') or ''
    if isinstance(v, list):
        p=[(x.get('text') or x.get('name') or x.get('value') or '') if isinstance(x,dict) else str(x) for x in v]
        return ' ; '.join(str(z) for z in p if z!='')
    return v

def fmt_date(ms):
    try: return datetime.datetime.fromtimestamp(float(ms)/1000, tz=VN).strftime('%d/%m/%Y')
    except Exception: return ''

def field_value(f, name):
    if name=='Ngày': return fmt_date(f.get('Ngày')) if f.get('Ngày') else ''
    return cell(f.get(name))

def read_view(t):
    out=[]; pt=None
    fields=['Số ĐH','Ngày','Tên SP','Số nhập','Minh chứng','Ghi chú']
    while True:
        p=f'/open-apis/bitable/v1/apps/{BASE}/tables/{SRC_TABLE}/records/search?page_size=500'+(('&page_token='+pt) if pt else '')
        d=api(t,'POST',p,{'view_id':SRC_VIEW,'field_names':fields})
        if d.get('_http'): raise SystemExit('Đọc Base lỗi: %s'%d)
        d=d['data']; out+=d.get('items',[])
        if d.get('has_more'): pt=d['page_token']
        else: break
    return out

def col_letter(n):
    s=''
    while n>0: n,r=divmod(n-1,26); s=chr(65+r)+s
    return s

def find_tab(t):
    meta=api(t,'GET',f'/open-apis/sheets/v2/spreadsheets/{SHEET_TOKEN}/metainfo')
    if meta.get('_http'): raise SystemExit('Không đọc được Sheet (scope/share?): %s'%meta)
    for s in meta.get('data',{}).get('sheets',[]):
        if norm(s.get('title'))==norm(SHEET_TAB_TITLE):
            return s.get('sheetId')
    raise SystemExit('Không thấy tab "%s" trong Sheet.'%SHEET_TAB_TITLE)

def read_headers(t, tab):
    d=api(t,'GET',f'/open-apis/sheets/v2/spreadsheets/{SHEET_TOKEN}/values/{tab}!A1:AZ1')
    if d.get('_http'): raise SystemExit('Đọc header lỗi: %s'%d)
    vals=d.get('data',{}).get('valueRange',{}).get('values',[]) or [[]]
    return vals[0] if vals else []

def used_rows(t, tab, col):
    d=api(t,'GET',f'/open-apis/sheets/v2/spreadsheets/{SHEET_TOKEN}/values/{tab}!{col}1:{col}100000')
    vals=d.get('data',{}).get('valueRange',{}).get('values',[]) or []
    n=0
    for i,r in enumerate(vals):
        if r and str(r[0]).strip(): n=i+1
    return n

def main():
    t=tok()
    items=read_view(t)
    print('Đọc view: %d bản ghi.'%len(items))
    if DRY_RUN:
        for it in items[:3]:
            f=it['fields']; print('  •',field_value(f,'Số ĐH'),'|',field_value(f,'Ngày'),'|',field_value(f,'Tên SP'),'|',field_value(f,'Số nhập'))
        print('DRY_RUN: không ghi Sheet.'); return
    tab=find_tab(t)
    headers=read_headers(t, tab)
    # map: cột (index 1-based) -> field nguồn
    colmap=[]
    for i,h in enumerate(headers, start=1):
        fld=HEADER2FIELD.get(norm(h))
        if fld: colmap.append((i, col_letter(i), h, fld))
    if not colmap: raise SystemExit('Không map được cột nào. Header đích: %s'%headers)
    print('Cột sẽ ghi:', ', '.join('%s="%s"<-%s'%(c,h,f) for _,c,h,f in colmap))
    n=len(items)
    # ghi từng cột dữ liệu (hàng 2..n+1), KHÔNG đụng cột khác
    ranges=[]
    for idx,col,h,fld in colmap:
        vals=[[field_value(it['fields'], fld)] for it in items]
        ranges.append({'range':f'{tab}!{col}2:{col}{n+1}','values':vals})
    d=api(t,'POST',f'/open-apis/sheets/v2/spreadsheets/{SHEET_TOKEN}/values_batch_update',{'valueRanges':ranges})
    if d.get('_http'): raise SystemExit('Ghi Sheet lỗi: %s'%d)
    # xoá dữ liệu dư ở CÁC CỘT ĐÃ MAP nếu lần trước dài hơn (không đụng cột công thức)
    first_col=colmap[0][1]
    prev=used_rows(t, tab, first_col)
    if prev>n+1:
        blanks=[['']*len(colmap) for _ in range(prev-(n+1))]
        # các cột map có thể không liền nhau -> xoá từng cột
        clr=[]
        for _,col,_,_ in colmap:
            clr.append({'range':f'{tab}!{col}{n+2}:{col}{prev}','values':[['']]*(prev-(n+1))})
        api(t,'POST',f'/open-apis/sheets/v2/spreadsheets/{SHEET_TOKEN}/values_batch_update',{'valueRanges':clr})
    print('Đã ghi %d dòng vào tab "%s" (giữ nguyên công thức các cột khác).'%(n, SHEET_TAB_TITLE))


if __name__=='__main__':
    main()

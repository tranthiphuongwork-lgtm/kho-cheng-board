# -*- coding: utf-8 -*-
"""
Đồng bộ (mirror) 1 VIEW của Lark Base -> 1 tab bảng-tính-thường trong Lark Sheet.
Nguồn : Base kế toán, bảng "Mua hàng", view vew3AfAswZ.
Đích  : Lark Sheet SPOEss..., tab tên "Đồng bộ Mua hàng" (tự tạo lại mỗi lần -> mirror sạch).
Cột   : Số ĐH · Ngày · Tên SP · Số nhập · Minh chứng · Ghi chú

LƯU Ý: các tab kiểu Bitable (Sheet9, XMXeCH...) KHÔNG ghi được bằng API ô tính,
nên script dùng một tab bảng-tính-thường riêng.

Chạy 1 lần khi bấm (workflow_dispatch). Cần secret: LARK_APP_ID, LARK_APP_SECRET, LARK_APP_TOKEN.
YÊU CẦU app: scope sheets:spreadsheet + được share Editor vào Sheet.
DRY_RUN=1 để chỉ đọc Base và in ra, KHÔNG ghi Sheet.
"""
import os, json, datetime, urllib.request, urllib.error

H='https://open.larksuite.com'
APP=os.environ['LARK_APP_ID']
SEC=os.environ['LARK_APP_SECRET']
BASE=os.environ['LARK_APP_TOKEN']
SRC_TABLE='tblsSoY9HERffH6A'
SRC_VIEW='vew3AfAswZ'
SHEET_TOKEN=os.environ.get('SHEET_TOKEN','SPOEssCrjhROBDtn9YHlrQIWgtb')
SHEET_TAB_TITLE=os.environ.get('SHEET_TAB_TITLE','Đồng bộ Mua hàng')
COLS=['Số ĐH','Ngày','Tên SP','Số nhập','Minh chứng','Ghi chú']
DRY_RUN=(os.getenv('DRY_RUN') or '').strip() in ('1','true','yes')
VN=datetime.timezone(datetime.timedelta(hours=7))


def tok():
    r=urllib.request.Request(H+'/open-apis/auth/v3/tenant_access_token/internal',
        data=json.dumps({'app_id':APP,'app_secret':SEC}).encode(),
        headers={'Content-Type':'application/json'},method='POST')
    return json.load(urllib.request.urlopen(r,timeout=30))['tenant_access_token']


def api(t, method, path, body=None):
    data=json.dumps(body).encode() if body is not None else None
    r=urllib.request.Request(H+path, data=data,
        headers={'Authorization':'Bearer '+t,'Content-Type':'application/json'}, method=method)
    try:
        return json.load(urllib.request.urlopen(r, timeout=60))
    except urllib.error.HTTPError as e:
        return {'_http': e.code, 'body': e.read().decode()[:400]}


def cell(v):
    if v is None: return ''
    if isinstance(v, dict):
        if 'value' in v:
            x=v['value']
            if isinstance(x, list): x=x[0] if x else ''
            return x
        return v.get('text') or v.get('name') or ''
    if isinstance(v, list):
        parts=[]
        for x in v:
            if isinstance(x, dict):
                parts.append(x.get('text') or x.get('name') or x.get('value') or '')
            else:
                parts.append(str(x))
        return ' ; '.join(str(p) for p in parts if p!='')
    return v


def fmt_date(ms):
    try:
        return datetime.datetime.fromtimestamp(float(ms)/1000, tz=VN).strftime('%d/%m/%Y')
    except Exception:
        return ''


def read_view(t):
    out=[]; pt=None
    while True:
        p=f'/open-apis/bitable/v1/apps/{BASE}/tables/{SRC_TABLE}/records/search?page_size=500'+(('&page_token='+pt) if pt else '')
        d=api(t,'POST',p,{'view_id':SRC_VIEW,'field_names':COLS})
        if d.get('_http'): raise SystemExit('Đọc Base lỗi: %s'%d)
        d=d['data']; out+=d.get('items',[])
        if d.get('has_more'): pt=d['page_token']
        else: break
    return out


def build_rows(items):
    rows=[COLS[:]]
    for it in items:
        f=it['fields']
        rows.append([
            cell(f.get('Số ĐH')),
            fmt_date(f.get('Ngày')) if f.get('Ngày') else '',
            cell(f.get('Tên SP')),
            cell(f.get('Số nhập')),
            cell(f.get('Minh chứng')),
            cell(f.get('Ghi chú')),
        ])
    return rows


def col_letter(n):
    s=''
    while n>0:
        n,r=divmod(n-1,26); s=chr(65+r)+s
    return s


def ensure_fresh_tab(t):
    """Xoá tab cùng tên nếu có, tạo lại mới -> trả sheetId (mirror luôn sạch)."""
    meta=api(t,'GET',f'/open-apis/sheets/v2/spreadsheets/{SHEET_TOKEN}/metainfo')
    if meta.get('_http'):
        raise SystemExit('Không đọc được Sheet (kiểm tra scope sheets:spreadsheet + share app vào Sheet): %s'%meta)
    for s in meta.get('data',{}).get('sheets',[]):
        if s.get('title')==SHEET_TAB_TITLE:
            api(t,'POST',f'/open-apis/sheets/v2/spreadsheets/{SHEET_TOKEN}/sheets_batch_update',
                {'requests':[{'deleteSheet':{'sheetId':s.get('sheetId')}}]})
    d=api(t,'POST',f'/open-apis/sheets/v2/spreadsheets/{SHEET_TOKEN}/sheets_batch_update',
          {'requests':[{'addSheet':{'properties':{'title':SHEET_TAB_TITLE}}}]})
    if d.get('_http'): raise SystemExit('Tạo tab lỗi: %s'%d)
    return d['data']['replies'][0]['addSheet']['properties']['sheetId']


def write_rows(t, tab_id, rows):
    end=col_letter(len(COLS)); nrow=len(rows)
    rng=f'{tab_id}!A1:{end}{nrow}'
    d=api(t,'PUT',f'/open-apis/sheets/v2/spreadsheets/{SHEET_TOKEN}/values',
          {'valueRange':{'range':rng,'values':rows}})
    if d.get('_http'): raise SystemExit('Ghi Sheet lỗi: %s'%d)
    return nrow-1


def main():
    t=tok()
    items=read_view(t)
    rows=build_rows(items)
    print('Đọc view: %d bản ghi -> %d dòng (kèm header).'%(len(items),len(rows)))
    print('Header:', ' | '.join(COLS))
    for r in rows[1:4]:
        print('  •', ' | '.join(str(x)[:22] for x in r))
    if DRY_RUN:
        print('\nDRY_RUN: chỉ đọc Base, KHÔNG ghi Sheet.'); return
    tab_id=ensure_fresh_tab(t)
    n=write_rows(t, tab_id, rows)
    print('\nĐã ghi %d dòng vào tab "%s" (id %s) — mirror xong.'%(n, SHEET_TAB_TITLE, tab_id))


if __name__=='__main__':
    main()

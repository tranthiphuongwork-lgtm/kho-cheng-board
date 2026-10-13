# -*- coding: utf-8 -*-
"""Ghi cac lan CHUYEN VI TRI PL -> D (khu sot) cua kho Au Co vao bang Xuat kho.

VI SAO CAN:
  Khi kho chuyen hang tu PL xuong sot, Lark ghi duoc ve 'Nhap sot' nhung thieu
  ve 'Xuat luu kho'. Hai cot lech nhau bao nhieu thi cot Ton sai bay nhieu.
  Job nay bu not ve con thieu.

NGUON: API MO cua Gobox (client_credentials) — KHONG dung GOBOX_WEB_TOKEN nua,
nen khong chet theo han token phien ERP 15 ngay.
    GET /open/api/warehouse-pickings
        ?type=1 (chuyen noi bo) & warehouse_id=32 & sort=id:-1
        & include[]=moves & include[]=moves.location & include[]=moves.locationDest
    moves[].location.code      vi tri di
    moves[].locationDest.code  vi tri den     (chu D viet HOA, kieu camelCase)
    moves[].external_code      G.SKU
    moves[].quantity_done      so da chuyen

KHONG GHI TRUNG: truoc khi ghi, doc bang Xuat kho va bo cac ma INT da co.

Bien moi truong
  LARK_APP_ID / LARK_APP_SECRET      bat buoc
  LARK_APP_TOKEN                     mac dinh = Base dang dung
  WAREHOUSE_ID                       mac dinh 32 (Au Co)
  NGAY_TU / NGAY_DEN                 'YYYY-MM-DD'. De trong = hom nay.
                                     Dat khoang rong de bu lich su.
  DRY_RUN=1                          chi in ra, khong ghi (mac dinh)
"""
import io
import os
import sys
import json
import time
import datetime
import urllib.parse
import urllib.request
import urllib.error

GOBOX = os.getenv('GOBOX_BASE', 'https://api.gobox.asia').rstrip('/')
CID = os.getenv('GOBOX_CLIENT_ID', '25')
CSEC = os.getenv('GOBOX_CLIENT_SECRET', 'bdEOeIp9yu6V8okBoP2UQcPAudHLuegDk4rIevOG')
LARK = os.getenv('LARK_HOST', 'https://open.larksuite.com')
BASE = os.getenv('LARK_APP_TOKEN', 'SA7ebfOdLaUJ5fsVILIl1QGag7b')
T_XK = os.getenv('LARK_TABLE_XUATKHO', 'tblIHtLsM4QTMMQJ')
WH = os.getenv('WAREHOUSE_ID', '32')
KHO = os.getenv('TEN_KHO', 'Kho Âu Cơ')
LOAI = 'Xuất lưu kho'
DRY = (os.getenv('DRY_RUN') or '1').strip() in ('1', 'true', 'yes')
VN = datetime.timezone(datetime.timedelta(hours=7))


def _goi(url, data=None, headers=None, method=None, tries=4, t=60):
    for i in range(tries):
        try:
            rq = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
            with urllib.request.urlopen(rq, timeout=t) as f:
                return json.loads(f.read().decode()), None
        except urllib.error.HTTPError as e:
            b = ''
            try:
                b = e.read().decode()[:250]
            except Exception:
                pass
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(2 * (i + 1)); continue
            return None, 'HTTP %d %s' % (e.code, b)
        except Exception as e:
            if i < tries - 1:
                time.sleep(2 * (i + 1)); continue
            return None, str(e)
    return None, '?'


def _ngay(s):
    """'13-10-2026 09:38:03' -> date"""
    try:
        return datetime.datetime.strptime(s[:10], '%d-%m-%Y').date()
    except Exception:
        return None


def _obj(x):
    if isinstance(x, dict) and 'data' in x:
        return x['data'] or {}
    return x or {}


hom_nay = datetime.datetime.now(VN).date()
tu = (datetime.date.fromisoformat(os.getenv('NGAY_TU'))
      if os.getenv('NGAY_TU') else hom_nay)
den = (datetime.date.fromisoformat(os.getenv('NGAY_DEN'))
       if os.getenv('NGAY_DEN') else hom_nay)
print('Khoang ngay: %s -> %s | kho %s' % (tu, den, WH))

# ---------------------------------------------------------------- Gobox
d, e = _goi(GOBOX + '/oauth/token',
            urllib.parse.urlencode({'grant_type': 'client_credentials',
                                    'client_id': CID,
                                    'client_secret': CSEC}).encode(),
            {'Content-Type': 'application/x-www-form-urlencoded',
             'Accept': 'application/json'}, 'POST')
if e:
    raise SystemExit('Token Gobox loi: ' + e)
GH = {'Authorization': 'Bearer ' + d['access_token'], 'Accept': 'application/json'}

moves, page, het = [], 1, False
while page <= 60 and not het:
    q = [('limit', '100'), ('page', str(page)), ('warehouse_id', WH),
         ('sort', 'id:-1'), ('type', '1'),
         ('include[]', 'moves'), ('include[]', 'moves.location'),
         ('include[]', 'moves.locationDest')]
    d, e = _goi(GOBOX + '/open/api/warehouse-pickings?' + urllib.parse.urlencode(q), headers=GH)
    if e:
        raise SystemExit('Doc warehouse-pickings loi: ' + e)
    ds = (d or {}).get('data') or []
    if not ds:
        break
    for r in ds:
        ng = _ngay(r.get('created_at') or '')
        if ng is None:
            continue
        if ng < tu:                       # da sort id:-1 nen qua moc la dung
            het = True
            continue
        if ng > den:
            continue
        if 'CHUY' not in (r.get('status_txt') or '').upper():
            continue                      # chi lay phieu DA chuyen xong
        mv = r.get('moves')
        for m in ((mv.get('data') if isinstance(mv, dict) else mv) or []):
            a = _obj(m.get('location')).get('code') or ''
            b = _obj(m.get('locationDest')).get('code') or ''
            sl = float(m.get('quantity_done') or m.get('quantity') or 0)
            g = str(m.get('external_code') or '').strip()
            if not (g and sl > 0):
                continue
            moves.append({'ma': r.get('code') or '', 'gio': r.get('created_at') or '',
                          'g': g, 'sl': sl, 'cu': a.upper(), 'moi': b.upper()})
    if len(ds) < 100:
        break
    page += 1
    time.sleep(0.2)

print('Doc duoc %d dong chuyen vi tri trong khoang.' % len(moves))
pl_d = [m for m in moves if m['cu'].startswith('PL')
        and (m['moi'].startswith('D') or m['moi'].startswith('KHAY')
             or m['moi'].startswith('KS'))]
print('  PL -> sot (D/khay): %d dong, %s sp'
      % (len(pl_d), '{:,.0f}'.format(sum(m['sl'] for m in pl_d))))
bo = [m for m in moves if m not in pl_d]
if bo:
    print('  bo qua %d dong khong phai PL->sot (vd %s)'
          % (len(bo), ', '.join('%s->%s' % (m['cu'], m['moi']) for m in bo[:3])))

if not pl_d:
    print('\nKhong co gi de ghi.')
    raise SystemExit

# ---------------------------------------------------------------- Lark
d, e = _goi(LARK + '/open-apis/auth/v3/tenant_access_token/internal',
            json.dumps({'app_id': os.environ['LARK_APP_ID'],
                        'app_secret': os.environ['LARK_APP_SECRET']}).encode(),
            {'Content-Type': 'application/json'}, 'POST')
if e:
    raise SystemExit('Token Lark loi: ' + e)
H = {'Authorization': 'Bearer ' + d['tenant_access_token'],
     'Content-Type': 'application/json'}


def gt(v):
    if isinstance(v, list):
        return ''.join(x.get('text', '') for x in v if isinstance(x, dict))
    if isinstance(v, dict):
        x = v.get('value')
        if isinstance(x, list) and x:
            return x[0].get('text') if isinstance(x[0], dict) else x[0]
        return x
    return v


da_co, pt = set(), ''
while True:
    u = (LARK + '/open-apis/bitable/v1/apps/%s/tables/%s/records/search?page_size=500'
         % (BASE, T_XK)) + (('&page_token=' + pt) if pt else '')
    d, e = _goi(u, json.dumps({'field_names': ['Ghi chú']}).encode(), H, 'POST')
    if e:
        raise SystemExit('Doc bang Xuat kho loi: ' + e)
    for it in d['data'].get('items', []):
        for tok in (gt(it['fields'].get('Ghi chú')) or '').replace('·', ' ').split():
            if tok.startswith('INT-'):
                da_co.add(tok)
    if not d['data'].get('has_more'):
        break
    pt = d['data']['page_token']
print('  Bang Xuat kho dang co %d ma INT.' % len(da_co))

moi = [m for m in pl_d if m['ma'] not in da_co]
print('  Da ghi truoc do : %d dong -> bo qua' % (len(pl_d) - len(moi)))
print('  SE GHI MOI      : %d dong, %s sp'
      % (len(moi), '{:,.0f}'.format(sum(m['sl'] for m in moi))))
if not moi:
    print('\nKhong co gi moi.')
    raise SystemExit

print()
print('%-14s %-20s %-10s %8s  %s' % ('Ma INT', 'Thoi gian', 'G.SKU', 'So luong', 'Vi tri'))
for m in sorted(moi, key=lambda x: x['gio'])[:20]:
    print('%-14s %-20s %-10s %8.0f  %s -> %s'
          % (m['ma'], m['gio'], m['g'], m['sl'], m['cu'], m['moi']))
if len(moi) > 20:
    print('   ... va %d dong nua' % (len(moi) - 20))

if DRY:
    print('\n(DRY_RUN — chua ghi vao Lark.)')
    raise SystemExit


def ms(s):
    try:
        return int(datetime.datetime.strptime(s, '%d-%m-%Y %H:%M:%S')
                   .replace(tzinfo=VN).timestamp() * 1000)
    except Exception:
        return int(datetime.datetime.now(VN).timestamp() * 1000)


n = 0
u = LARK + '/open-apis/bitable/v1/apps/%s/tables/%s/records/batch_create' % (BASE, T_XK)
for i in range(0, len(moi), 100):
    lo = moi[i:i + 100]
    body = {'records': [{'fields': {
        'Ngày đóng gói': ms(m['gio']),
        'G SKU': m['g'],
        'Số lượng': m['sl'],
        'Kho xuất': KHO,
        'Loại': LOAI,
        'Ghi chú': '%s · %s -> %s' % (m['ma'], m['cu'], m['moi']),
    }} for m in lo]}
    d, e = _goi(u, json.dumps(body).encode(), H, 'POST')
    if e or (d or {}).get('code') != 0:
        print('LOI sau %d dong: %s' % (n, e or json.dumps(d, ensure_ascii=False)[:200]))
        break
    n += len(lo)
    print('  da ghi %d/%d' % (n, len(moi)))
    time.sleep(0.3)
print('\nXong: ghi %d dong "Xuất lưu kho".' % n)

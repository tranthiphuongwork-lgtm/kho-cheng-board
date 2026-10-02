# -*- coding: utf-8 -*-
"""Đối chiếu tồn kho Gobox vs Lark, gửi cảnh báo vào nhóm Bot của Phương.

  Gobox kho 32 "Online Cheng"  <->  Lark cột "Tồn kho Âu Cơ"
  Gobox kho 65 "Kho Mê Linh"   <->  Lark cột "Kho Mê Linh 1" + "Kho Mê Linh 2"

Chạy trên GitHub Actions. Secret cần: LARK_APP_ID, LARK_APP_SECRET, LARK_APP_TOKEN,
GOBOX_CLIENT_ID, GOBOX_CLIENT_SECRET.
ENV tuỳ chọn: DRY_RUN=1 (chỉ in, không gửi), MIN_LECH=<số> (bỏ qua lệch nhỏ hơn),
LARK_CONFIRM_CHAT=<chat_id nhóm nhận>.
"""
import os, json, re, time, urllib.request, urllib.parse, urllib.error, datetime

LARK_HOST = 'https://open.larksuite.com'
GB = os.getenv('GOBOX_BASE', 'https://api.gobox.asia').rstrip('/')
APP_ID = os.environ['LARK_APP_ID']
APP_SEC = os.environ['LARK_APP_SECRET']
BASE = os.environ['LARK_APP_TOKEN']
GCID = os.environ['GOBOX_CLIENT_ID']
GSEC = os.environ['GOBOX_CLIENT_SECRET']
T_SP = 'tbl7PSQh3Lq5Tlxy'
CHAT = (os.getenv('LARK_CONFIRM_CHAT') or 'oc_d284fd22a122a942ba6985414ecf0352').strip()
DRY = (os.getenv('DRY_RUN') or '').strip() in ('1', 'true', 'yes')
MIN_LECH = float(os.getenv('MIN_LECH') or 1)
# Cac ma hang ngau nhien / cung dong: chi can TONG cua nhom khop la duoc,
# khong canh bao tung ma (vi don ngau nhien duoc lay tu bat ky mau nao trong nhom).
NHOM = [('Hũ ủ · nhóm 3 mã', ['hrd', 'huhong', 'hutim']),
        ('Ủ gói · nhóm 3 mã', ['ubio', 'uhong', 'utim']),
        # Nuoc hoa 2ML: tru z2ml (Blue Shirt) va lk2ml (LADYKILLER) theo yeu cau
        ('Nước hoa 2ML · nhóm 6 mã', ['db2ml', 'fl2ml', 'gp2ml', 'ja2ml',
                                      'vial2mlrd', 'vn2ml'])]
WH = {32: 'Âu Cơ', 65: 'Mê Linh'}
VN = datetime.timezone(datetime.timedelta(hours=7))

def req(u, data=None, headers=None, method=None, tries=5, t=90):
    last = None
    for i in range(tries):
        r = urllib.request.Request(u, data=data, headers=headers or {},
                                   method=method or ('POST' if data else 'GET'))
        try:
            return json.load(urllib.request.urlopen(r, timeout=t)), None
        except urllib.error.HTTPError as e:
            return None, '%s %s' % (e.code, e.read().decode()[:400])
        except Exception as e:
            last = e; time.sleep(2 * (i + 1))
    return None, str(last)

def gt(v):
    if isinstance(v, list): return ''.join(x.get('text', '') for x in v if isinstance(x, dict))
    if isinstance(v, dict):
        x = v.get('value')
        if isinstance(x, list) and x:
            y = x[0]; return gt(y) if isinstance(y, (dict, list)) else str(y)
        return str(v.get('text') or '')
    return str(v or '')

def fv(v):
    if isinstance(v, dict) and 'value' in v:
        x = v['value']; v = x[0] if isinstance(x, list) and x else 0
    if isinstance(v, list): v = v[0] if v else 0
    try: return float(v)
    except Exception: return 0.0

# ---------------- Lark ----------------
d, e = req(LARK_HOST + '/open-apis/auth/v3/tenant_access_token/internal',
           json.dumps({'app_id': APP_ID, 'app_secret': APP_SEC}).encode(),
           {'Content-Type': 'application/json'})
if e: raise SystemExit('Lark token lỗi: ' + e)
LTOK = d['tenant_access_token']
LH = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + LTOK}

items, pt = [], None
while True:
    u = LARK_HOST + f'/open-apis/bitable/v1/apps/{BASE}/tables/{T_SP}/records/search?page_size=500'
    if pt: u += '&page_token=' + pt
    d, e = req(u, json.dumps({'field_names': ['G SKU', 'SKU', 'Tên sản phẩm',
                                              'Tồn kho Âu Cơ', 'Kho Mê Linh 1', 'Kho Mê Linh 2']}).encode(), LH)
    if e: raise SystemExit('Đọc Tổng sản phẩm lỗi: ' + e)
    d = d['data']; items += d.get('items', [])
    if d.get('has_more'): pt = d['page_token']
    else: break

lark = {}
for it in items:
    f = it['fields']
    sku = gt(f.get('SKU')).strip()
    if not sku: continue
    lark[sku] = {'ten': gt(f.get('Tên sản phẩm')) or sku,
                 32: fv(f.get('Tồn kho Âu Cơ')),
                 65: fv(f.get('Kho Mê Linh 1')) + fv(f.get('Kho Mê Linh 2'))}
print('Lark: %d mã có SKU' % len(lark))

# ---------------- Gobox ----------------
d, e = req(GB + '/oauth/token',
           urllib.parse.urlencode({'grant_type': 'client_credentials',
                                   'client_id': GCID, 'client_secret': GSEC}).encode(),
           {'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'})
if e: raise SystemExit('Gobox token lỗi: ' + e)
GH = {'Authorization': 'Bearer ' + d['access_token'], 'Accept': 'application/json'}

def ton_gobox(skus):
    """Gobox tu choi CA LO neu 1 ma khong ton tai -> bo cac vi tri loi roi thu lai."""
    out, la = {}, list(skus)
    for _ in range(3):
        if not la: break
        u = GB + '/open/api/product-skus/quantity-in-warehouse?' + urllib.parse.urlencode(
            {'skus[]': la}, doseq=True)
        d, e = req(u, headers=GH)
        if not e:
            for sku, arr in (d.get('data') or {}).items():
                g = out.setdefault(sku, {32: 0.0, 65: 0.0})
                for w in arr or []:
                    if w.get('warehouse_id') in g:
                        g[w['warehouse_id']] += float(w.get('total_quantity') or 0)
            return out
        if '422' not in e:
            print('  lỗi lô: %s' % e[:160]); return out
        bad = set(int(m) for m in re.findall(r'skus\.(\d+)', e))
        if not bad:
            print('  lỗi lô không rõ: %s' % e[:160]); return out
        la = [x for j, x in enumerate(la) if j not in bad]
    return out

skus = sorted(lark)
gobox = {}
for i in range(0, len(skus), 50):
    gobox.update(ton_gobox(skus[i:i+50]))
    time.sleep(0.25)
print('Gobox: %d mã có dữ liệu tồn' % len(gobox))

# ---------------- So sánh ----------------
trong_nhom = set()
units = []          # (ma_hien_thi, {'ten':...}, ton_lark, ton_gobox)
for ten, ms in NHOM:
    co = [m for m in ms if m in lark and m in gobox]
    if not co: continue
    trong_nhom.update(ms)
    units.append(('+'.join(co), {'ten': ten},
                  {32: sum(lark[m][32] for m in co), 65: sum(lark[m][65] for m in co)},
                  {32: sum(gobox[m][32] for m in co), 65: sum(gobox[m][65] for m in co)}))
for sku, L in lark.items():
    if sku in trong_nhom or sku not in gobox: continue
    units.append((sku, L, {32: L[32], 65: L[65]}, gobox[sku]))

ca_hai, mot_kho = [], []
for ma, L, lt, G in units:
    d32, d65 = G[32] - lt[32], G[65] - lt[65]
    n32, n65 = abs(d32) >= MIN_LECH, abs(d65) >= MIN_LECH
    if n32 and n65: ca_hai.append((ma, {**L, 32: lt[32], 65: lt[65]}, G, d32, d65))
    elif n32 or n65: mot_kho.append((ma, {**L, 32: lt[32], 65: lt[65]}, G, d32, d65))
ca_hai.sort(key=lambda x: -(abs(x[3]) + abs(x[4])))
mot_kho.sort(key=lambda x: -(abs(x[3]) + abs(x[4])))
sosanh = len(units)
print('Đối chiếu được %d mã | lệch cả 2 kho: %d | lệch 1 kho: %d'
      % (sosanh, len(ca_hai), len(mot_kho)))

def dong(r):
    sku, L, G, d32, d65 = r
    p = []
    if abs(d32) >= MIN_LECH: p.append('Âu Cơ GB %d / Lark %d (**%+d**)' % (G[32], L[32], d32))
    if abs(d65) >= MIN_LECH: p.append('Mê Linh GB %d / Lark %d (**%+d**)' % (G[65], L[65], d65))
    return '**%s** · %s\n   %s' % (L['ten'][:40], sku, ' · '.join(p))

now = datetime.datetime.now(VN).strftime('%d/%m %H:%M')
if not ca_hai and not mot_kho:
    body = '✅ Không có mã nào lệch tồn (đối chiếu %d mã).' % sosanh
else:
    body = ('Đối chiếu **%d mã** lúc %s.\n'
            '**Lệch ở CẢ 2 kho: %d mã** · lệch 1 kho: %d mã\n\n'
            % (sosanh, now, len(ca_hai), len(mot_kho)))
    if ca_hai:
        body += '**── Lệch cả 2 kho ──**\n' + '\n'.join(dong(r) for r in ca_hai[:15]) + '\n'
        if len(ca_hai) > 15: body += '_… và %d mã nữa_\n' % (len(ca_hai) - 15)
    if mot_kho:
        body += '\n**── Chỉ lệch 1 kho ──**\n' + '\n'.join(dong(r) for r in mot_kho[:10])
        if len(mot_kho) > 10: body += '\n_… và %d mã nữa_' % (len(mot_kho) - 10)

thieu = [s for s in lark if s not in gobox and s not in trong_nhom]
foot = ('\n\n_Bỏ qua chênh lệch < %g. Đối chiếu: Gobox kho 32 Online Cheng ↔ Tồn kho Âu Cơ, '
        'Gobox kho 65 Kho Mê Linh ↔ Kho Mê Linh 1 + 2._' % MIN_LECH)
if thieu:
    foot += '\n_%d mã trong Tổng sản phẩm không có trên Gobox (vd: %s)._' % (
        len(thieu), ', '.join(sorted(thieu)[:5]))
body += foot

card = {'config': {'wide_screen_mode': True},
        'header': {'title': {'tag': 'plain_text', 'content': '📦 Đối chiếu tồn kho Gobox ↔ Lark'},
                   'template': 'orange' if (ca_hai or mot_kho) else 'green'},
        'elements': [{'tag': 'div', 'text': {'tag': 'lark_md', 'content': body}}]}

print('\n----- NỘI DUNG THẺ -----')
print(body[:2000])
if DRY:
    print('\n(DRY_RUN: không gửi Lark.)')
    raise SystemExit
d, e = req(LARK_HOST + '/open-apis/im/v1/messages?receive_id_type=chat_id',
           json.dumps({'receive_id': CHAT, 'msg_type': 'interactive',
                       'content': json.dumps(card)}).encode(), LH)
print('\nGửi nhóm %s: %s' % (CHAT, e or d.get('msg')))

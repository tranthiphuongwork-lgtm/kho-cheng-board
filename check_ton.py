# -*- coding: utf-8 -*-
"""Đối chiếu tồn kho Gobox vs Lark, gửi cảnh báo vào nhóm Bot của Phương.

  Gobox kho 32 "Online Cheng"  <->  Lark cột "Tồn kho Âu Cơ"
  Gobox kho 65 "Kho Mê Linh"   <->  Lark cột "Kho Mê Linh 1" + "Kho Mê Linh 2"

Chạy trên GitHub Actions. Secret cần: LARK_APP_ID, LARK_APP_SECRET, LARK_APP_TOKEN,
GOBOX_CLIENT_ID, GOBOX_CLIENT_SECRET.
ENV tuỳ chọn: DRY_RUN=1 (chỉ in, không gửi), MIN_LECH=<số> (bỏ qua lệch nhỏ hơn),
LARK_CONFIRM_CHAT=<chat_id nhóm nhận>.
"""
import os, io, json, re, time, urllib.request, urllib.parse, urllib.error, datetime

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


# ---------------- Trang HTML ----------------
now = datetime.datetime.now(VN)

def hang(r, nhom):
    ma, L, G, d32, d65 = r
    return {'ma': ma, 'ten': L['ten'], 'nhom': nhom,
            'acg': int(G[32]), 'acl': int(L[32]), 'acd': int(d32),
            'mlg': int(G[65]), 'mll': int(L[65]), 'mld': int(d65)}

rows = [hang(r, 2) for r in ca_hai] + [hang(r, 1) for r in mot_kho]
rows.sort(key=lambda x: -(abs(x['acd']) + abs(x['mld'])))
thieu = sorted(s for s in lark if s not in gobox and s not in trong_nhom)
am = [r for r in rows if r['acl'] < 0 or r['mll'] < 0]
meta = {'ngay': now.strftime('%d/%m/%Y %H:%M'), 'sosanh': sosanh, 'ca_hai': len(ca_hai),
        'mot_kho': len(mot_kho), 'nguong': MIN_LECH, 'am': len(am),
        'thieu': thieu, 'rows': rows}

TPL = """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Đối chiếu tồn kho Gobox ↔ Lark</title><style>
:root{--bg:#f6f7fb;--card:#fff;--ink:#16181d;--mut:#6b7280;--line:#e5e7eb;
      --up:#c2410c;--down:#1d4ed8;--bad:#dc2626}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
.wrap{max-width:1320px;margin:0 auto;padding:0 16px 48px}
header{background:linear-gradient(135deg,#0f766e,#0891b2);color:#fff;padding:26px 0 30px;margin-bottom:-18px}
header .wrap{padding-bottom:0}
h1{margin:0;font-size:21px;font-weight:650}
.sub{opacity:.85;font-size:13px;margin-top:4px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:0 0 18px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;
      box-shadow:0 1px 3px rgba(16,24,40,.06)}
.tile b{display:block;font-size:26px;font-weight:680;line-height:1.1}
.tile span{color:var(--mut);font-size:12px}
.bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
input,select{font:inherit;padding:9px 12px;border:1px solid var(--line);border-radius:9px;background:#fff}
input{flex:1;min-width:220px}
.cnt{color:var(--mut);font-size:13px;flex:0 0 auto}
.box{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow-x:auto;
     box-shadow:0 1px 3px rgba(16,24,40,.06)}
table{width:100%;min-width:1000px;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{padding:9px 12px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{position:sticky;background:#f9fafb;font-size:12px;color:var(--mut);font-weight:600;
   text-transform:uppercase;letter-spacing:.3px;z-index:1}
.h1 th{top:0}
.h2 th{top:31px;font-size:11px}
.grp{text-align:center;color:var(--ink);font-size:12px;border-left:1px solid var(--line)}
.grp.ml{border-left:2px solid #cbd5e1}
td.ml:first-of-type{border-left:2px solid #f1f5f9}
th.c1,td.c1{text-align:left;white-space:normal}
th.c1.ten,td.c1.ten{min-width:250px}
/* Loc 1 kho -> an han 3 cot cua kho con lai cho de doc. */
table.an-ml .ml{display:none}
table.an-ac .ac{display:none}
table.an-ml,table.an-ac{min-width:700px}
td:nth-child(1){color:var(--mut);font-size:12px}
tbody tr:hover{background:#f9fafb}
.ma{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:var(--mut)}
.up{color:var(--up);font-weight:650}.down{color:var(--down);font-weight:650}
.neg{color:var(--bad);font-weight:650}
.tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px;
     background:#fef3c7;color:#92400e;margin-left:6px}
.tag.one{background:#e0e7ff;color:#3730a3}
.note{color:var(--mut);font-size:12.5px;margin:14px 0 0;line-height:1.7}
.sep{border-top:1px solid var(--line);margin:22px 0 14px;padding-top:14px}
h2{font-size:14px;margin:0 0 8px;color:var(--mut);text-transform:uppercase;letter-spacing:.3px}
</style></head><body>
<header><div class="wrap"><h1>📦 Đối chiếu tồn kho Gobox ↔ Lark</h1>
<div class="sub" id="sub"></div></div></header>
<div class="wrap">
<div class="tiles" id="tiles"></div>
<div class="bar">
  <input id="q" placeholder="Tìm theo mã hoặc tên sản phẩm…">
  <span id="cnt" class="cnt"></span>
  <select id="f">
    <option value="all">Tất cả mã lệch</option>
    <option value="2">Lệch ở cả 2 kho</option>
    <option value="1">Chỉ lệch 1 kho</option>
    <option value="ac">Lệch kho Âu Cơ</option>
    <option value="ml">Lệch kho Mê Linh</option>
    <option value="neg">Chỉ mã tồn Lark âm</option>
  </select>
</div>
<div class="box"><table>
<thead>
<tr class="h1"><th rowspan="2">#</th><th rowspan="2" class="c1 ten">Sản phẩm</th><th rowspan="2" class="c1">Mã</th>
<th colspan="3" class="grp ac">Kho Âu Cơ</th><th colspan="3" class="grp ml">Kho Mê Linh</th></tr>
<tr class="h2"><th class="ac">Gobox</th><th class="ac">Lark</th><th class="ac">Lệch</th>
<th class="ml">Gobox</th><th class="ml">Lark</th><th class="ml">Lệch</th></tr></thead>
<tbody id="tb"></tbody></table></div>
<div id="extra"></div>
<p class="note" id="foot"></p>
</div>
<script>
const D = __DATA__;
const n = v => v.toLocaleString('vi-VN');
const sg = v => (v > 0 ? '+' : '') + n(v);
document.getElementById('sub').textContent =
  'Cập nhật ' + D.ngay + ' · bỏ qua chênh lệch nhỏ hơn ' + D.nguong;
document.getElementById('tiles').innerHTML = [
  ['Mã đối chiếu', D.sosanh, ''],
  ['Lệch ở cả 2 kho', D.ca_hai, 'up'],
  ['Chỉ lệch 1 kho', D.mot_kho, ''],
  ['Mã tồn Lark âm', D.am, 'neg']
].map(t => '<div class="tile"><b class="' + t[2] + '">' + n(t[1]) +
     '</b><span>' + t[0] + '</span></div>').join('');

const cell = (v, isDiff, kho) => {
  let c = kho;
  if (isDiff) c += v > 0 ? ' up' : (v < 0 ? ' down' : '');
  else if (v < 0) c += ' neg';
  return '<td class="' + c + '">' + (isDiff ? sg(v) : n(v)) + '</td>';
};
function draw() {
  const q = document.getElementById('q').value.trim().toLowerCase();
  const f = document.getElementById('f').value;
  let r = D.rows;
  if (f === '2') r = r.filter(x => x.nhom === 2);
  else if (f === '1') r = r.filter(x => x.nhom === 1);
  else if (f === 'neg') r = r.filter(x => x.acl < 0 || x.mll < 0);
  else if (f === 'ac') r = r.filter(x => Math.abs(x.acd) >= D.nguong);
  else if (f === 'ml') r = r.filter(x => Math.abs(x.mld) >= D.nguong);
  if (q) r = r.filter(x => (x.ten + ' ' + x.ma).toLowerCase().includes(q));
  // Loc theo 1 kho thi xep theo muc lech cua chinh kho do.
  if (f === 'ac') r = r.slice().sort((a, b) => Math.abs(b.acd) - Math.abs(a.acd));
  else if (f === 'ml') r = r.slice().sort((a, b) => Math.abs(b.mld) - Math.abs(a.mld));
  document.getElementById('cnt').textContent = r.length + ' mã';
  // Chon 1 kho -> an 3 cot cua kho con lai.
  const tb = document.querySelector('table');
  tb.classList.toggle('an-ml', f === 'ac');
  tb.classList.toggle('an-ac', f === 'ml');
  document.getElementById('tb').innerHTML = r.map((x, i) =>
    '<tr><td>' + (i + 1) + '</td><td class="c1 ten">' + x.ten +
    (x.nhom === 2 ? '<span class="tag">cả 2 kho</span>'
                  : '<span class="tag one">1 kho</span>') +
    '</td><td class="c1 ma">' + x.ma + '</td>' +
    cell(x.acg, 0, 'ac') + cell(x.acl, 0, 'ac') + cell(x.acd, 1, 'ac') +
    cell(x.mlg, 0, 'ml') + cell(x.mll, 0, 'ml') + cell(x.mld, 1, 'ml') + '</tr>').join('')
    || '<tr><td colspan="9" style="text-align:center;color:#6b7280;padding:28px">Không có mã nào khớp bộ lọc.</td></tr>';
}
document.getElementById('q').addEventListener('input', draw);
document.getElementById('f').addEventListener('change', draw);
draw();
if (D.thieu.length) document.getElementById('extra').innerHTML =
  '<div class="sep"><h2>' + D.thieu.length +
  ' mã trong Tổng sản phẩm nhưng Gobox không có tồn</h2><div class="box" style="padding:12px 14px">' +
  '<span class="ma">' + D.thieu.join(', ') + '</span></div></div>';
document.getElementById('foot').innerHTML =
  'Đối chiếu: Gobox kho 32 <b>Online Cheng</b> ↔ cột <b>Tồn kho Âu Cơ</b> · ' +
  'Gobox kho 65 <b>Kho Mê Linh</b> ↔ <b>Kho Mê Linh 1 + Kho Mê Linh 2</b>. ' +
  'Kho 47 (Cửa hàng) và kho 7 (Gobox Hà Nội) không tính.<br>' +
  'Lệch = Gobox − Lark: <span class="up">số dương</span> là Gobox nhiều hơn, ' +
  '<span class="down">số âm</span> là Lark nhiều hơn. ' +
  'Các nhóm hàng ngẫu nhiên được cộng gộp, chỉ so tổng của nhóm.';
</script></body></html>"""

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ton_lech.html')
io.open(out, 'w', encoding='utf-8').write(TPL.replace('__DATA__', json.dumps(meta, ensure_ascii=False)))
print('Da ghi', out)

# ---------------- Thẻ Lark (ngắn, chỉ dẫn link) ----------------
URL = ('https://tranthiphuongwork-lgtm.github.io/kho-cheng-board/ton_lech.html?v='
       + str(int(now.timestamp())))
if not rows:
    body = '✅ Không có mã nào lệch tồn — đối chiếu **%d mã** (ngưỡng %g).' % (sosanh, MIN_LECH)
else:
    top = rows[0]
    body = ('Đối chiếu **%d mã** lúc %s.\n'
            'Lệch ở **cả 2 kho: %d mã** · chỉ 1 kho: **%d mã** · tồn Lark âm: **%d mã**.\n'
            'Nặng nhất: **%s** (Âu Cơ %+d · Mê Linh %+d).'
            % (sosanh, now.strftime('%d/%m %H:%M'), len(ca_hai), len(mot_kho), len(am),
               top['ten'][:38], top['acd'], top['mld']))
card = {'config': {'wide_screen_mode': True},
        'header': {'title': {'tag': 'plain_text', 'content': '📦 Đối chiếu tồn kho Gobox ↔ Lark'},
                   'template': 'orange' if rows else 'green'},
        'elements': [{'tag': 'div', 'text': {'tag': 'lark_md', 'content': body}}]}
if rows:
    card['elements'].append({'tag': 'action', 'actions': [
        {'tag': 'button', 'text': {'tag': 'plain_text', 'content': 'Xem danh sách lệch tồn'},
         'type': 'primary', 'url': URL}]})

print('\n----- NỘI DUNG THẺ -----')
print(body)
print('Link:', URL)
if DRY:
    print('\n(DRY_RUN: không gửi Lark.)')
    raise SystemExit
d, e = req(LARK_HOST + '/open-apis/im/v1/messages?receive_id_type=chat_id',
           json.dumps({'receive_id': CHAT, 'msg_type': 'interactive',
                       'content': json.dumps(card)}).encode(), LH)
print('\nGửi nhóm %s: %s' % (CHAT, e or d.get('msg')))

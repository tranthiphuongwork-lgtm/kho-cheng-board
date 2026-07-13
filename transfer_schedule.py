# -*- coding: utf-8 -*-
"""Lịch luân chuyển hàng về kho vệ tinh (B4) -> dashboard GitHub Pages + thẻ Lark.
Chạy ngày 15,17,25,27:
 - 15 & 25: DANH SÁCH CHUẨN BỊ (Mê Linh soạn hàng trước).
 - 17 & 27: LỆNH CHUYỂN chính thức.
Ưu tiên lấy Mê Linh 1 (kho tổng, cho hết); ML1 hết mới lấy Mê Linh 2
(ML2 giữ tối thiểu ROT_ML2_KEEP_DAYS ngày bán của chính nó).
Âu Cơ điền tới ROT_AC_DAYS ngày. Chuyển TRÒN THÙNG theo Quy cách.
Bảng chi tiết có cột: SL chuyển · số thùng · Tồn tối thiểu kho xuất · Tồn còn lại.
"""
import os, math, json, html, datetime, urllib.request
from collections import defaultdict
import cloud_update as M

AC_DAYS       = float(os.getenv("ROT_AC_DAYS", "30"))
ML2_DAYS      = float(os.getenv("ROT_ML2_DAYS", "30"))
ML2_KEEP_DAYS = float(os.getenv("ROT_ML2_KEEP_DAYS", "15"))
PAGES_URL     = os.getenv("ROT_PAGES_URL", "https://tranthiphuongwork-lgtm.github.io/kho-cheng-board/transfer.html")
OUT_HTML      = os.getenv("ROT_OUT_HTML", "transfer.html")
VN = datetime.timezone(datetime.timedelta(hours=7))

def build_rows(tok):
    may = M.may_cache(); shopee = M.shopee_rates(tok)
    tp = M.lsearch(tok, M.T_SP, ['G SKU','Tên sản phẩm','Phân loại','Hãng','Tồn kho Âu Cơ',
                                 'Kho Mê Linh 1','Kho Mê Linh 2','Quy cách'])
    inv = {}
    for it in tp:
        f = it['fields']; g = M.gt(f.get('G SKU'))
        if not g: continue
        inv[str(g)] = {
            'name': M.gt(f.get('Tên sản phẩm')) or str(g),
            'cat': (M.gt(f.get('Phân loại')) or '').strip() or 'Khác',
            'hang': (M.gt(f.get('Hãng')) or '—').strip(),
            'qc': M.fv(f.get('Quy cách')),
            'ac': M.fv(f.get('Tồn kho Âu Cơ')), 'ml1': M.fv(f.get('Kho Mê Linh 1')),
            'ml2': M.fv(f.get('Kho Mê Linh 2')),
        }
    xk = M.lsearch(tok, M.T_XK, ['G SKU','Số lượng','Kho xuất','Ngày đóng gói'])
    salesw = defaultdict(lambda: defaultdict(float)); days = set()
    for it in xk:
        f = it['fields']; g = M.gt(f.get('G SKU')); q = f.get('Số lượng') or 0; k = f.get('Kho xuất')
        d = f.get('Ngày đóng gói')
        if isinstance(d, (int, float)): days.add(d)
        if g and k: salesw[str(g)][k] += q
    NDW = max(1, len(days)); NDM = 31
    def rate(g, kho, shp_key):
        wk = salesw.get(g, {}).get(kho, 0)
        mo = (may.get(g, {}) or {}).get(shp_key, 0) if isinstance(may.get(g), dict) else 0
        sh = shopee.get(g, {}).get(shp_key, 0)
        return max(wk / NDW, mo / NDM) + sh
    rows = []
    for g, v in inv.items():
        if g in M.TRIO: continue
        v = {**v, 'g': g, 'ar': rate(g, 'Kho Âu Cơ', 'ac'), 'mr': rate(g, 'Kho Mê Linh 2', 'ml2')}
        rows.append(v)
    return rows

def plan_transfers(rows):
    out = []
    for v in rows:
        qc = v['qc'] or 0
        def tron(x): return int(math.floor(x / qc) * qc) if qc > 0 else int(x)
        ac_t  = math.ceil(v['ar'] * AC_DAYS)
        ml2_t = math.ceil(v['mr'] * ML2_DAYS)
        ml2_min = math.ceil(v['mr'] * ML2_KEEP_DAYS)   # ML2 giữ tối thiểu
        ml1_left, ml2_left, ac = v['ml1'], v['ml2'], v['ac']
        ml1_av  = max(0, ml1_left)          # ML1 cho hết -> tối thiểu 0
        ml2_sur = max(0, ml2_left - ml2_min)
        # 1) Âu Cơ thiếu -> ML1 trước, rồi ML2 (giữ ml2_min)
        need = max(0, ac_t - ac)
        for src in ('Mê Linh 1', 'Mê Linh 2'):
            if need <= 0: break
            avail = ml1_av if src == 'Mê Linh 1' else ml2_sur
            mv = tron(min(need, avail))
            if mv <= 0: continue
            need -= mv
            if src == 'Mê Linh 1':
                ml1_av -= mv; ml1_left -= mv
                out.append({'src': src, 'dst': 'Âu Cơ', **v, 'qty': mv, 'src_min': 0, 'src_left': int(ml1_left)})
            else:
                ml2_sur -= mv; ml2_left -= mv
                out.append({'src': src, 'dst': 'Âu Cơ', **v, 'qty': mv, 'src_min': int(ml2_min), 'src_left': int(ml2_left)})
        # 2) ML2 thiếu -> lấy ML1
        need2 = max(0, ml2_t - v['ml2'])
        if need2 > 0 and ml1_av > 0:
            mv = tron(min(need2, ml1_av))
            if mv > 0:
                ml1_av -= mv; ml1_left -= mv
                out.append({'src': 'Mê Linh 1', 'dst': 'Mê Linh 2', **v, 'qty': mv, 'src_min': 0, 'src_left': int(ml1_left)})
    return out

# ---------- Dashboard HTML ----------
def _vn(n):
    try: return f"{int(n):,}".replace(",", ".")
    except: return str(n)
def _esc(s): return html.escape(str(s))

ROUTE_ORDER = ['Mê Linh 1 → Âu Cơ', 'Mê Linh 2 → Âu Cơ', 'Mê Linh 1 → Mê Linh 2']

def build_dashboard_html(transfers, mode, ngay):
    routes = defaultdict(list); grand = 0
    for t in transfers:
        routes[f"{t['src']} → {t['dst']}"].append(t); grand += t['qty']
    keys = sorted(routes, key=lambda k: ROUTE_ORDER.index(k) if k in ROUTE_ORDER else 99)
    mode_txt = "CHUẨN BỊ hàng để chuyển" if mode == 'prep' else "LỆNH CHUYỂN KHO"
    sections = ""
    for k in keys:
        items = routes[k]; sub = sum(i['qty'] for i in items)
        cats = defaultdict(list)
        for it in items: cats[it['cat']].append(it)
        rows_html = ""
        idx = 0
        for cat in sorted(cats, key=lambda c: -sum(i['qty'] for i in cats[c])):
            ci = sorted(cats[cat], key=lambda i: -i['qty'])
            csub = sum(i['qty'] for i in ci)
            rows_html += f'<tr class=cathead><td></td><td>📂 {_esc(cat)} <span class=mut>({len(ci)} mã)</span></td><td>{_vn(csub)}</td><td colspan=3></td></tr>'
            for it in ci:
                idx += 1
                qc = it['qc'] or 0
                box = f'{int(it["qty"]/qc)} thùng' if qc and it["qty"] % qc == 0 else '—'
                rows_html += (f'<tr><td class=stt>{idx}</td><td class=name>{_esc(it["name"])}</td>'
                              f'<td class=q>{_vn(it["qty"])}</td><td>{box}</td>'
                              f'<td>{_vn(it["src_min"])}</td><td>{_vn(it["src_left"])}</td></tr>')
        sections += (f'<div class=route><h3><span>🔄 {_esc(k)}</span><span>{_vn(sub)} sp · {len(items)} mã</span></h3>'
                     f'<table><thead><tr><th class=stt>#</th><th>Sản phẩm</th><th>SL chuyển</th><th>Số thùng</th>'
                     f'<th>Tồn tối thiểu<br>kho xuất</th><th>Tồn còn lại<br>kho xuất</th></tr></thead><tbody>'
                     f'{rows_html}</tbody></table></div>')
    return f"""<!DOCTYPE html><html lang=vi><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{mode_txt} — {ngay}</title><style>
*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f4f6fb;color:#1f2933;padding:16px;max-width:1100px;margin:0 auto}}
h1{{font-size:20px;color:#1F4E78}}.sub{{color:#667085;font-size:13px;margin:6px 0 14px}}
.route{{margin:16px 0}}.route h3{{font-size:15px;color:#fff;background:linear-gradient(135deg,#e67e22,#d35400);padding:10px 14px;border-radius:10px 10px 0 0;display:flex;justify-content:space-between}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:0 0 10px 10px;overflow:hidden;box-shadow:0 1px 4px rgba(16,24,40,.06)}}
th,td{{padding:8px 9px;font-size:12.5px;text-align:right;border-bottom:1px solid #eef0f4}}th{{background:#2E75B6;color:#fff;white-space:nowrap;font-size:11.5px}}
th:nth-child(2),td.name{{text-align:left}}td.stt,th.stt{{text-align:center;color:#98a2b3;width:34px}}
tr:hover td{{background:#f8fafc}}.q{{font-weight:700;color:#d35400}}.mut{{color:#98a2b3;font-weight:400}}
tr.cathead td{{background:#fdf1e7;font-weight:700;color:#d35400;font-size:12px}}
.foot{{color:#98a2b3;font-size:11px;margin-top:14px;text-align:center}}</style></head><body>
<h1>{'📋' if mode=='prep' else '🔄'} {mode_txt} — {ngay}</h1>
<div class=sub>{'Danh sách để kho Mê Linh soạn trước (chuyển vào ngày 17/27).' if mode=='prep' else 'Thực hiện chuyển hôm nay.'}
· Tổng <b>{_vn(sum(t['qty'] for t in transfers))}</b> sp · Ưu tiên lấy Mê Linh 1, ML1 hết mới lấy Mê Linh 2 (ML2 giữ tối thiểu {int(ML2_KEEP_DAYS)} ngày bán).</div>
{sections}
<div class=foot>Tự động · Kho Cheng · Âu Cơ mục tiêu {int(AC_DAYS)} ngày · Cột "Tồn còn lại" = tồn kho xuất sau khi trừ SL chuyển.</div>
</body></html>"""

def build_card(transfers, mode, ngay, url):
    grand = sum(t['qty'] for t in transfers)
    routes = defaultdict(lambda: [0, 0])
    for t in transfers:
        r = routes[f"{t['src']} → {t['dst']}"]; r[0] += 1; r[1] += t['qty']
    lines = [f"• {k}: **{_vn(q)}** sp ({n} mã)" for k, (n, q) in
             sorted(routes.items(), key=lambda x: ROUTE_ORDER.index(x[0]) if x[0] in ROUTE_ORDER else 99)]
    title = "📋 CHUẨN BỊ hàng để chuyển" if mode == 'prep' else "🔄 LỆNH CHUYỂN KHO"
    tmpl = 'orange' if mode == 'prep' else 'turquoise'
    body = (f"**Ngày {ngay}** · Tổng **{_vn(grand)}** sp\n" + "\n".join(lines))
    return {"config": {"wide_screen_mode": True},
            "header": {"template": tmpl, "title": {"tag": "plain_text", "content": title}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": body}},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "📋 Mở bảng chi tiết"},
                     "type": "primary", "url": url}]},
            ]}

def send(card):
    body = {"msg_type": "interactive", "card": card}
    urllib.request.urlopen(urllib.request.Request(
        M.WEBHOOK, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST"), timeout=30)

def main():
    now = datetime.datetime.now(VN); day = now.day
    mode = os.getenv("ROT_MODE") or ({15: 'prep', 25: 'prep', 17: 'transfer', 27: 'transfer'}.get(day))
    if not mode:
        print(f"Hôm nay ngày {day} không phải 15/17/25/27 -> bỏ qua."); return
    tok = M.ltoken()
    transfers = plan_transfers(build_rows(tok))
    if not transfers:
        print("Không có hàng cần chuyển."); return
    ngay = now.strftime('%d/%m/%Y')
    open(OUT_HTML, 'w', encoding='utf-8').write(build_dashboard_html(transfers, mode, ngay))
    send(build_card(transfers, mode, ngay, PAGES_URL))
    print(f"Đã ghi {OUT_HTML} + gửi thẻ {mode}: {len(transfers)} dòng.")

if __name__ == '__main__':
    main()

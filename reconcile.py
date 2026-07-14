# -*- coding: utf-8 -*-
"""Doi chieu DOANH THU don POS chuyen khoan (Gobox) vs GIAO DICH TIEN VAO (Lark 'Sao ke').

  1) Lay TAT CA don POS -> chia nhom PTTT: chuyen khoan / tien mat / khac.
  2) Lay giao dich loai 'in' tu bang 'Sao ke' (Lark Base) trong khoang ngay.
  3) Khop don CHUYEN KHOAN <-> tien vao theo SO TIEN (uu tien ma don trong noi dung).
  4) Phan loai: matched / order_no_txn / txn_no_order.  Bao ca TONG TIEN MAT.

Xuat Excel nhieu sheet + gui thong bao (thẻ chi tiet + dinh kem file) len Lark.

Chay:
  python reconcile.py 2026-07-14
  python reconcile.py 2026-07-01 2026-07-14 --no-notify
"""
import os, sys, json, datetime
import larkbase as L
import gobox_orders as GO

TZ = datetime.timezone(datetime.timedelta(hours=7))
try:
    import config as C
except Exception:
    C = None

SAOKE_TABLE  = os.getenv("GOBOX_SAOKE_TABLE", "tblQ4FASSV9Y6Ewl")
F_SK_AMOUNT  = os.getenv("SAOKE_AMOUNT_FIELD", "số tiền")
F_SK_CONTENT = os.getenv("SAOKE_CONTENT_FIELD", "Nội dung")
F_SK_TYPE    = os.getenv("SAOKE_TYPE_FIELD", "Loại giao dịch")
F_SK_DATE    = os.getenv("SAOKE_DATE_FIELD", "Ngày giao dịch")
F_SK_ID      = os.getenv("SAOKE_ID_FIELD", "ID")
IN_VALUE     = os.getenv("SAOKE_IN_VALUE", "in")
TOLERANCE    = int(os.getenv("RECON_TOLERANCE", "0"))
CARD_MAX     = int(os.getenv("RECON_CARD_MAX", "20"))   # so dong toi da liet ke moi nhom tren thẻ
CONFIRM_CHAT = os.getenv("LARK_CONFIRM_CHAT_ID",
                         getattr(C, "CONFIRM_CHAT_ID", "") if C else "") or "oc_d284fd22a122a942ba6985414ecf0352"
NOTIFY_DEFAULT = os.getenv("RECON_NOTIFY", "1") == "1"


def _to_date(ts_ms):
    try:
        return datetime.datetime.fromtimestamp(int(ts_ms) / 1000, TZ).date().isoformat()
    except Exception:
        return ""


def saoke_in(start_date, end_date):
    t = L.token()
    rows = L.list_records(t, SAOKE_TABLE, [F_SK_AMOUNT, F_SK_CONTENT, F_SK_TYPE, F_SK_DATE, F_SK_ID])
    out = []
    for it in rows:
        f = it["fields"]
        if L.gt(f.get(F_SK_TYPE)) != IN_VALUE:
            continue
        d = _to_date(f.get(F_SK_DATE))
        if not (start_date <= d <= end_date):
            continue
        amt = L.gt(f.get(F_SK_AMOUNT))
        try:
            amt = float(amt)
        except (TypeError, ValueError):
            continue
        out.append({"amount": amt, "content": L.gt(f.get(F_SK_CONTENT)) or "",
                    "id": L.gt(f.get(F_SK_ID)) or it.get("record_id"), "date": d})
    return out


def reconcile(orders, txns):
    txns = [dict(x, _used=False) for x in txns]
    matched, order_no_txn = [], []

    def _by_code(o):
        code = (o.get("code") or "").strip()
        if not code or len(code) < 4:
            return None
        for x in txns:
            if not x["_used"] and code in (x["content"] or ""):
                return x
        return None

    def _by_amount(o):
        cands = o.get("amounts") or ([o["amount"]] if o.get("amount") else [])
        best = None
        for x in txns:
            if x["_used"]:
                continue
            if not any(abs(x["amount"] - c) <= TOLERANCE for c in cands):
                continue
            if best is None or (x["date"] == o["date"] and best["date"] != o["date"]):
                best = x
        return best

    for o in orders:
        x = _by_code(o)
        if x:
            x["_used"] = True; matched.append({"order": o, "txn": x, "by": "code"}); o["_done"] = True
    for o in orders:
        if o.get("_done"):
            continue
        x = _by_amount(o)
        if x:
            x["_used"] = True; matched.append({"order": o, "txn": x, "by": "amount"})
        else:
            order_no_txn.append(o)
    txn_no_order = [x for x in txns if not x["_used"]]
    return matched, order_no_txn, txn_no_order


def run(start_date, end_date):
    g, oerr = GO.classify(start_date, end_date)
    if oerr:
        return {"ok": False, "stage": "gobox_orders", "err": oerr, "start": start_date, "end": end_date}
    orders = g["transfer"]
    txns = saoke_in(start_date, end_date)
    matched, order_no_txn, txn_no_order = reconcile(orders, txns)
    return {
        "ok": True, "start": start_date, "end": end_date,
        "n_orders": len(orders), "sum_orders": sum(o["amount"] or 0 for o in orders),
        "n_cash": len(g["cash"]), "sum_cash": sum(o["amount"] or 0 for o in g["cash"]),
        "n_other": len(g["other"]), "sum_other": sum(o["amount"] or 0 for o in g["other"]),
        "n_txn_in": len(txns), "sum_txn_in": sum(x["amount"] or 0 for x in txns),
        "n_matched": len(matched), "sum_matched": sum(m["order"]["amount"] or 0 for m in matched),
        "n_order_no_txn": len(order_no_txn), "sum_order_no_txn": sum(o["amount"] or 0 for o in order_no_txn),
        "n_txn_no_order": len(txn_no_order), "sum_txn_no_order": sum(x["amount"] or 0 for x in txn_no_order),
        "matched": matched, "order_no_txn": order_no_txn, "txn_no_order": txn_no_order,
        "cash_orders": g["cash"], "other_orders": g["other"],
    }


def _fmt(n):
    return f"{int(round(n or 0)):,}".replace(",", ".")


def summary_text(r):
    if not r.get("ok"):
        return "LOI (" + str(r.get("stage", "?")) + "): " + str(r.get("err"))
    return "\n".join([
        f"Doi chieu {r['start']}..{r['end']}",
        f"- Don POS chuyen khoan: {r['n_orders']} · {_fmt(r['sum_orders'])} d",
        f"- Don POS tien mat: {r['n_cash']} · {_fmt(r['sum_cash'])} d",
        f"- Tien vao (Sao ke 'in'): {r['n_txn_in']} · {_fmt(r['sum_txn_in'])} d",
        f"- KHOP: {r['n_matched']} don · {_fmt(r['sum_matched'])} d",
        f"- Don CK chua thay tien vao: {r['n_order_no_txn']} · {_fmt(r['sum_order_no_txn'])} d",
        f"- Tien vao chua khop don: {r['n_txn_no_order']} · {_fmt(r['sum_txn_no_order'])} d",
    ])


# ---------------- THẺ LARK ----------------
def build_card(r):
    def _pct(a, b):
        return f" ({a/b*100:.0f}%)" if b else ""
    tmpl = "green" if r["n_order_no_txn"] == 0 else "orange"
    title = f"📊 Doi chieu CK vs tien vao · {r['start']}" + (f"..{r['end']}" if r['end'] != r['start'] else "")

    top = "\n".join([
        f"**Don POS chuyen khoan:** {r['n_orders']} · {_fmt(r['sum_orders'])} d",
        f"💵 **Don POS tien mat:** {r['n_cash']} · {_fmt(r['sum_cash'])} d",
        f"**Tien vao (in):** {r['n_txn_in']} · {_fmt(r['sum_txn_in'])} d",
        f"✅ **Khop:** {r['n_matched']}{_pct(r['n_matched'], r['n_orders'])} · {_fmt(r['sum_matched'])} d",
    ])

    def _list_block(title_line, lines):
        more = ""
        shown = lines[:CARD_MAX]
        if len(lines) > CARD_MAX:
            more = f"\n_… và {len(lines) - CARD_MAX} dòng khác (xem Excel)_"
        return title_line + ("\n" + "\n".join(shown) if shown else "") + more

    ord_lines = [f"• `{o['code'] or '(không mã)'}` — **{_fmt(o['amount'])} d**  _{o.get('date','')}_"
                 for o in r["order_no_txn"]]
    txn_lines = [f"• **{_fmt(x['amount'])} d** — {(x['content'] or '')[:40]}  _{x.get('date','')}_"
                 for x in r["txn_no_order"]]

    blk_ord = _list_block(f"⚠️ **Don CK chua thay tien vao: {r['n_order_no_txn']} · {_fmt(r['sum_order_no_txn'])} d**", ord_lines)
    blk_txn = _list_block(f"❔ **Tien vao chua khop don: {r['n_txn_no_order']} · {_fmt(r['sum_txn_no_order'])} d**", txn_lines)

    return {"config": {"wide_screen_mode": True},
            "header": {"template": tmpl, "title": {"tag": "plain_text", "content": title}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": top}},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": blk_ord}},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": blk_txn}},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": "File Excel chi tiet dinh kem ben duoi."}]},
            ]}


# ---------------- XUAT EXCEL ----------------
def write_xlsx(r, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook()
    hdr_fill = PatternFill("solid", fgColor="1F4E78"); hdr_font = Font(color="FFFFFF", bold=True); money = '#,##0'

    def _sheet(title, headers, rows, money_cols=()):
        ws = wb.create_sheet(title); ws.append(headers)
        for c in range(1, len(headers) + 1):
            cell = ws.cell(1, c); cell.fill = hdr_fill; cell.font = hdr_font; cell.alignment = Alignment(horizontal="center")
        for row in rows:
            ws.append(row)
        for mc in money_cols:
            for row in range(2, ws.max_row + 1):
                ws.cell(row, mc).number_format = money
        for col in range(1, len(headers) + 1):
            w = max([len(str(headers[col-1]))] + [len(str(ws.cell(rr, col).value or "")) for rr in range(2, ws.max_row + 1)])
            ws.column_dimensions[ws.cell(1, col).column_letter].width = min(max(w + 2, 10), 48)
        ws.freeze_panes = "A2"; return ws

    ws = wb.active; ws.title = "Tong hop"
    ws["A1"] = "DOI CHIEU DON POS CHUYEN KHOAN vs TIEN VAO"; ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = f"Ky: {r['start']} .. {r['end']}"
    ws.append([]); ws.append(["Nhom", "So don/GD", "So tien (d)"])
    for c in range(1, 4):
        cell = ws.cell(4, c); cell.fill = hdr_fill; cell.font = hdr_font; cell.alignment = Alignment(horizontal="center")
    for name, n, s in [
        ("Don POS chuyen khoan", r["n_orders"], r["sum_orders"]),
        ("Don POS tien mat", r["n_cash"], r["sum_cash"]),
        ("Don POS PTTT khac", r["n_other"], r["sum_other"]),
        ("Tien vao (Sao ke 'in')", r["n_txn_in"], r["sum_txn_in"]),
        ("KHOP", r["n_matched"], r["sum_matched"]),
        ("Don CK khong thay tien vao", r["n_order_no_txn"], r["sum_order_no_txn"]),
        ("Tien vao khong khop don", r["n_txn_no_order"], r["sum_txn_no_order"]),
    ]:
        ws.append([name, n, s])
    for row in range(5, ws.max_row + 1):
        ws.cell(row, 3).number_format = money
    ws.column_dimensions["A"].width = 32; ws.column_dimensions["B"].width = 12; ws.column_dimensions["C"].width = 18

    _sheet("Khop", ["Ma don", "Ngay don", "Doanh thu don (d)", "So tien vao (d)", "Noi dung tien vao", "ID GD", "Khop theo"],
           [[m["order"]["code"], m["order"]["date"], m["order"]["amount"], m["txn"]["amount"],
             m["txn"]["content"], m["txn"]["id"], m["by"]] for m in r["matched"]], money_cols=(3, 4))
    _sheet("Don CK chua co tien vao", ["Ma don", "Ngay don", "Doanh thu don (d)", "PTTT"],
           [[o["code"], o["date"], o["amount"], o.get("pay_txt", "")] for o in r["order_no_txn"]], money_cols=(3,))
    _sheet("Tien vao chua co don", ["Ngay", "So tien (d)", "Noi dung", "ID GD"],
           [[x["date"], x["amount"], x["content"], x["id"]] for x in r["txn_no_order"]], money_cols=(2,))
    _sheet("Don tien mat", ["Ma don", "Ngay don", "So tien (d)", "PTTT"],
           [[o["code"], o["date"], o["amount"], o.get("pay_txt", "")] for o in r.get("cash_orders", [])], money_cols=(3,))
    wb.save(path); return path


# ---------------- GUI LARK ----------------
def _upload_file(token, path, fname):
    import urllib.request, uuid, json as _j
    HOST = getattr(C, "HOST", "https://open.larksuite.com")
    boundary = "----recon" + uuid.uuid4().hex
    with open(path, "rb") as f:
        content = f.read()
    parts = []
    def _add(name, value):
        parts.append(("--" + boundary).encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode()); parts.append(b"")
        parts.append(str(value).encode())
    _add("file_type", "stream"); _add("file_name", fname)
    parts.append(("--" + boundary).encode())
    parts.append(f'Content-Disposition: form-data; name="file"; filename="{fname}"'.encode())
    parts.append(b"Content-Type: application/octet-stream"); parts.append(b""); parts.append(content)
    parts.append(("--" + boundary + "--").encode()); parts.append(b"")
    data = b"\r\n".join(parts)
    req = urllib.request.Request(HOST + "/open-apis/im/v1/files", data=data, method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "multipart/form-data; boundary=" + boundary})
    d = _j.load(urllib.request.urlopen(req, timeout=60))
    return d.get("data", {}).get("file_key"), d


def notify(r, xlsx_path=None, chat_id=None):
    import messaging as M, urllib.request, json as _j
    t = L.token(); chat = chat_id or CONFIRM_CHAT; out = {"card": None, "file": None}
    try:
        out["card"] = M.send_card(chat, build_card(r), t)
    except Exception as e:
        out["card"] = {"err": str(e)}
    if xlsx_path:
        try:
            fk, _ = _upload_file(t, xlsx_path, os.path.basename(xlsx_path))
            if fk:
                HOST = getattr(C, "HOST", "https://open.larksuite.com")
                body = {"receive_id": chat, "msg_type": "file", "content": _j.dumps({"file_key": fk})}
                req = urllib.request.Request(HOST + "/open-apis/im/v1/messages?receive_id_type=chat_id",
                    data=_j.dumps(body).encode(), method="POST",
                    headers={"Authorization": "Bearer " + t, "Content-Type": "application/json"})
                out["file"] = _j.load(urllib.request.urlopen(req, timeout=30))
        except Exception as e:
            out["file"] = {"err": str(e)}
    return out


if __name__ == "__main__":
    flags = [a for a in sys.argv[1:] if a.startswith("-")]
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    start = args[0] if args else datetime.datetime.now(TZ).date().isoformat()
    end = args[1] if len(args) > 1 else start
    do_notify = NOTIFY_DEFAULT and "--no-notify" not in flags
    r = run(start, end)
    print(summary_text(r))
    if r.get("ok"):
        xlsx = f"reconcile_{start.replace('-','')}_{end.replace('-','')}.xlsx"
        try:
            write_xlsx(r, xlsx); print("Excel:", xlsx)
        except Exception as e:
            xlsx = None; print("Xuat Excel loi (can openpyxl):", e)
        if do_notify:
            res = notify(r, xlsx)
            print("Lark:", json.dumps({k: (v.get("code") if isinstance(v, dict) else v) for k, v in res.items()}, ensure_ascii=False))
    slim = {k: v for k, v in r.items() if k not in ("matched", "order_no_txn", "txn_no_order", "cash_orders", "other_orders")}
    print(json.dumps(slim, ensure_ascii=False))

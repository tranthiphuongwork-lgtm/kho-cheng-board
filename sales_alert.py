# -*- coding: utf-8 -*-
"""Tinh binh quan ban/thang + tang truong tuan; SP nao vuot 1.5 lan -> canh bao.
So ban = so xuat kho (warehouse-export-by-sku) o CA 2 kho gop lai.

Cua so:
  - Tuan hien tai:  [D-6 .. D]                (7 ngay)
  - Nen (binh quan): [D-34 .. D-7]            (28 ngay = 4 tuan truoc do)
  - binh_quan_tuan = tong_nen / 4
  - Canh bao neu tuan >  NGUONG * binh_quan_tuan  va  tuan >= MIN_WEEK_QTY
"""
import os, datetime
import gobox as G
import larkbase as L
import config as C

NGUONG       = float(os.getenv("ALERT_RATIO", "1.5"))     # vuot 1.5 lan
MIN_WEEK_QTY = float(os.getenv("ALERT_MIN_WEEK_QTY", "10"))  # bo qua SP ban qua it (tranh bao gia)
TOP_N        = int(os.getenv("ALERT_TOP_N", "30"))
TZ           = datetime.timezone(datetime.timedelta(hours=7))  # gio VN


def _name_map():
    """Map G SKU -> Ten san pham tu bang Tong san pham (de the canh bao de doc)."""
    try:
        t = L.token()
        m = {}
        for it in L.list_records(t, C.T_SP, ["G SKU", "Ten san pham", "Tên sản phẩm"]):
            f = it["fields"]
            g = L.gt(f.get("G SKU"))
            nm = L.gt(f.get("Tên sản phẩm")) or L.gt(f.get("Ten san pham"))
            if g and nm:
                m[str(g)] = nm
        return m
    except Exception:
        return {}

def _today():
    return datetime.datetime.now(TZ).date()

def _dstr(d):
    return d.strftime("%Y-%m-%d")

def _row_date(r):
    s = (r.get("pickup_at") or r.get("done_at") or "")[:10]
    try:
        return datetime.date.fromisoformat(s)
    except Exception:
        return None

def compute(token=None):
    """Tra ve dict ket qua: {ok, wh_found, cur_start.., alerts:[...], err}."""
    tok, err = (token, None) if token else G.get_token()
    if err:
        return {"ok": False, "err": err}
    found, whs, err = G.resolve_warehouse_ids(tok)
    if err:
        return {"ok": False, "err": "list kho: " + err}
    if not found:
        names = ", ".join(w.get("name", "?") for w in (whs or [])[:20])
        return {"ok": False, "err": "Khong tim thay kho khop ten. Kho hien co: " + names}

    D = _today()
    cur_start, cur_end = D - datetime.timedelta(days=6), D
    base_start, base_end = D - datetime.timedelta(days=34), D - datetime.timedelta(days=7)

    # gom du lieu 35 ngay cho ca 2 kho
    cur = {}   # gsku -> qty tuan nay
    base = {}  # gsku -> qty 28 ngay nen
    label = {} # gsku -> nhan hien thi
    for wh_name, wh_id in found.items():
        rows, err = G.export_by_sku(tok, wh_id, _dstr(base_start), _dstr(cur_end))
        if err:
            return {"ok": False, "err": f"xuat kho {wh_name}: {err}"}
        for r in rows:
            k = str(r.get("gsku"))
            q = float(r.get("quantity") or 0)
            dt = _row_date(r)
            if dt is None:
                continue
            label.setdefault(k, G.row_label(r))
            if cur_start <= dt <= cur_end:
                cur[k] = cur.get(k, 0) + q
            elif base_start <= dt <= base_end:
                base[k] = base.get(k, 0) + q

    nmap = _name_map()
    for k in list(label.keys()):
        if k in nmap:
            label[k] = nmap[k]

    alerts = []
    for k, cq in cur.items():
        if cq < MIN_WEEK_QTY:
            continue
        avg = base.get(k, 0) / 4.0
        if avg <= 0:
            ratio = None  # SP moi / thang truoc khong ban
            trigger = cq >= MIN_WEEK_QTY
        else:
            ratio = cq / avg
            trigger = ratio > NGUONG
        if trigger:
            alerts.append({"sku": label.get(k, k), "gsku": k,
                           "week": cq, "avg_week": avg, "ratio": ratio})
    # sap xep: SP moi (ratio None) len dau, roi theo ratio giam dan
    alerts.sort(key=lambda a: (a["ratio"] is not None, -(a["ratio"] or 9e9)))
    return {"ok": True, "wh_found": found,
            "cur_start": _dstr(cur_start), "cur_end": _dstr(cur_end),
            "base_start": _dstr(base_start), "base_end": _dstr(base_end),
            "n_sku": len(cur), "alerts": alerts[:TOP_N], "n_alert": len(alerts)}

def _fmt(n):
    try:
        return f"{n:,.0f}".replace(",", ".")
    except Exception:
        return str(n)

def build_alert_card(res):
    kho = " + ".join(f"{k} (#{v})" for k, v in res["wh_found"].items())
    head = (f"**Tuan:** {res['cur_start']} -> {res['cur_end']}  "
            f"(so sanh binh quan tuan cua 28 ngay truoc)\n"
            f"**Kho:** {kho}\n"
            f"**Nguong canh bao:** > {NGUONG:g} lan binh quan  ·  bo qua SP < {int(MIN_WEEK_QTY)}/tuan")
    lines = []
    for a in res["alerts"]:
        if a["ratio"] is None:
            lines.append(f"• **{a['sku']}** — tuan nay **{_fmt(a['week'])}**, thang truoc ~0  🆕 *(moi tang manh)*")
        else:
            lines.append(f"• **{a['sku']}** — tuan nay **{_fmt(a['week'])}** vs BQ tuan {_fmt(a['avg_week'])}  → **x{a['ratio']:.1f}**")
    body = "\n".join(lines) if lines else "_Khong co SP nao vuot nguong._"
    extra = ""
    if res["n_alert"] > len(res["alerts"]):
        extra = f"\n\n_… va {res['n_alert'] - len(res['alerts'])} SP khac (hien {len(res['alerts'])}/{res['n_alert']})._"
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": "red",
                   "title": {"tag": "plain_text", "content": "\U0001f4c8 Canh bao ban tang dot bien"}},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": head}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": body + extra}},
        ],
    }

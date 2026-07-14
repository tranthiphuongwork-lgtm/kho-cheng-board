# -*- coding: utf-8 -*-
"""DO Gobox: thu nhieu BASE de tim cai xin duoc token, roi do endpoint don hang.
    python probe_run.py 2026-07-14
"""
import sys, os, json, datetime
import gobox as GB
import gobox_orders as GO
TZ = datetime.timezone(datetime.timedelta(hours=7))
d = sys.argv[1] if len(sys.argv) > 1 else datetime.datetime.now(TZ).date().isoformat()

sec = GB.CSEC or ""
print("CLIENT_ID :", repr(GB.CID))
print("SECRET    :", (sec[:4] + "..." + sec[-4:]) if len(sec) > 8 else "(rong)", "| do dai:", len(sec))
print("GRANT     :", repr(GB.GRANT))
print("=" * 60)

# Danh sach base ung vien: uu tien GOBOX_BASE (env) neu co, roi cac base pho bien
cands = []
env_base = os.getenv("GOBOX_BASE", "").strip().rstrip("/")
if env_base:
    cands.append(env_base)
for b in ["https://dev-api.gobox.asia", "https://api.gobox.asia",
          "http://dev-api.gobox.asia", "http://api.gobox.asia"]:
    if b not in cands:
        cands.append(b)

good = None
for b in cands:
    GB.BASE = b
    GB._TOK = {"val": None, "exp": 0}
    tok, terr = GB.get_token(force=True)
    if tok:
        print("BASE", b, "-> TOKEN OK (do dai %d)" % len(tok))
        good = b
        break
    else:
        # rut gon loi cho de doc
        msg = str(terr)
        print("BASE", b, "-> LOI:", (msg[:140] + "...") if len(msg) > 140 else msg)

if not good:
    print("\n>>> KHONG base nao xin duoc token. Kiem tra lai client_id/secret voi ben Gobox.")
    sys.exit(0)

print("\n===> BASE DUNG:", good, " (dat GOBOX_BASE = base nay)")
print("=" * 60)
GB.BASE = good
GB._TOK = {"val": None, "exp": 0}
rep = GO.probe(d, d)
print("Helper enum PTTT:", "loi " + str(rep.get("helpers_err")) if rep.get("helpers_err") else "OK")
print("helpers_sample:", json.dumps(rep.get("helpers_sample"), ensure_ascii=False)[:800])
for e in rep.get("tried", []):
    print("\n--- Endpoint:", e["path"], "| so ban ghi:", e["n"], "| loi:", e["err"])
    if e.get("sample_keys"):
        print("   Cac truong:", e["sample_keys"])
        print("   Doan  ma don :", e.get("guess_code"))
        print("   Doan doanh thu:", e.get("guess_amount"))
        print("   Doan PTTT(txt):", e.get("guess_paytxt"))
        print("   Don mau:", json.dumps(e.get("sample"), ensure_ascii=False)[:1400])
print("\n===== JSON DAY DU =====")
print(json.dumps(rep, ensure_ascii=False))

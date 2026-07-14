# -*- coding: utf-8 -*-
"""Chay DO endpoint Gobox + in ket qua de doc (dung tren GitHub Actions/Render log).
    python probe_run.py 2026-07-14
"""
import sys, json, datetime
import gobox_orders as GO
TZ = datetime.timezone(datetime.timedelta(hours=7))
d = sys.argv[1] if len(sys.argv) > 1 else datetime.datetime.now(TZ).date().isoformat()
rep = GO.probe(d, d)
print("BASE:", rep.get("base"))
if not rep.get("ok"):
    print("LOI:", rep.get("err")); sys.exit(0)
he = rep.get("helpers_err")
print("Helper (enum PTTT) loi:" , he if he else "OK - xem helpers_sample de tim ma 'Chuyen khoan'/'Tien mat'")
for e in rep.get("tried", []):
    print("\n--- Endpoint:", e["path"], "| so ban ghi:", e["n"], "| loi:", e["err"])
    if e.get("sample_keys"):
        print("   Cac truong:", e["sample_keys"])
        print("   Doan  ma don :", e.get("guess_code"))
        print("   Doan doanh thu:", e.get("guess_amount"))
        print("   Doan PTTT(txt):", e.get("guess_paytxt"))
        print("   Doan ngay     :", e.get("guess_date"))
print("\n===== JSON DAY DU (copy gui lai de chot cau hinh) =====")
print(json.dumps(rep, ensure_ascii=False))

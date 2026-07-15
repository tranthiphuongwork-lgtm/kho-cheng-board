# -*- coding: utf-8 -*-
"""Kiem tra ghi chu 'igfb' nam o truong nao & danh sach co tra ve khong.
    python probe_run.py"""
import sys, os, json, datetime, urllib.request, urllib.parse
import gobox as GB
TZ = datetime.timezone(datetime.timedelta(hours=7))
DAY = "2026-07-14"
CODES = [a for a in sys.argv[1:] if not a.startswith("-")] or ["1784007125908","1784001611790","1784008445241"]

def GET(path, params=None):
    url = GB.BASE + path + (("?" + urllib.parse.urlencode(params or {}, doseq=True)) if params else "")
    data, err = GB._open(urllib.request.Request(url, headers={"Authorization":"Bearer "+TOK,"Accept":"application/json"}), timeout=90)
    return data, err

TOK=None
for b in [os.getenv("GOBOX_BASE","").strip().rstrip("/"),"https://api.gobox.asia"]:
    if not b: continue
    GB.BASE=b; GB._TOK={"val":None,"exp":0}
    t,e=GB.get_token(force=True)
    if t: TOK=t; break
print("BASE:",GB.BASE); print("="*60)

NOTEK=["internal_notes","message_to_seller","note","notes","remark","description","tags","label"]
print(">> DON CHI TIET (detail):")
for code in CODES:
    data,_=GET("/open/api/orders/"+code)
    o=(data or {}).get("data",data) if isinstance(data,dict) else {}
    if not isinstance(o,dict): print("  ",code,"loi"); continue
    notes={k:o.get(k) for k in NOTEK if k in o}
    print("  ",code,"| igfb-in-raw:", "igfb" in json.dumps(o,ensure_ascii=False).lower(),
          "| total:",o.get("total_amount"),"| notes:", json.dumps(notes,ensure_ascii=False))

print("\n>> TIM TRONG DANH SACH (list) 2026-07-14, xem list co ghi chu khong:")
found={}
for page in range(1,40):
    data,_=GET("/open/api/orders",{"start_date":DAY,"end_date":DAY,"limit":100,"page":page})
    rows=(data or {}).get("data",[]) or []
    for r in rows:
        if str(r.get("transaction_no")) in CODES:
            notes={k:r.get(k) for k in NOTEK if k in r}
            found[str(r["transaction_no"])]={"igfb": "igfb" in json.dumps(r,ensure_ascii=False).lower(),"notes":notes}
    if len(found)>=len(CODES) or len(rows)<100: break
for code in CODES:
    print("  ",code,"->", json.dumps(found.get(code,"KHONG THAY TRONG LIST"),ensure_ascii=False))

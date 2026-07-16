# -*- coding: utf-8 -*-
"""Dump tat ca truong CHUOI khong rong cua don chi tiet -> tim truong 'Ghi chu'.
    python probe_run.py 1784080521057 1784080610728"""
import sys, os, json, urllib.request
import gobox as GB
CODES=[a for a in sys.argv[1:] if not a.startswith("-")] or ["1784080521057","1784080610728","1784107685748"]
def GET(path):
    d,err=GB._open(urllib.request.Request(GB.BASE+path,headers={"Authorization":"Bearer "+TOK,"Accept":"application/json"}),timeout=60)
    return d,err
TOK=None
for b in [os.getenv("GOBOX_BASE","").strip().rstrip("/"),"https://api.gobox.asia"]:
    if not b: continue
    GB.BASE=b; GB._TOK={"val":None,"exp":0}
    t,e=GB.get_token(force=True)
    if t: TOK=t; break
print("BASE:",GB.BASE); print("="*60)
for code in CODES:
    d,err=GET("/open/api/orders/"+code)
    o=(d or {}).get("data",d) if isinstance(d,dict) else {}
    if not isinstance(o,dict): print(code,"loi",err); continue
    print("### Don",code,"- cac truong CHUOI khong rong:")
    for k,v in o.items():
        if isinstance(v,str) and v.strip():
            print("   ",k,"=",repr(v))
    print("-"*60)

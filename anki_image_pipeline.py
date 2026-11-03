#!/usr/bin/env python3
"""Add explicitly mapped, openly licensed Wikimedia Commons images to an existing APKG."""
import argparse, hashlib, json, mimetypes, os, re, shutil, sqlite3, tempfile, time, zipfile
from pathlib import Path
import requests

API="https://commons.wikimedia.org/w/api.php"
S=requests.Session()
S.headers.update({"User-Agent":"NewAnkiMedicalImagePipeline/1.0 (educational use; contact: replace-me@example.com)"})
ALLOWED={"cc0","public domain","cc by 4.0","cc by 3.0","cc by-sa 4.0","cc by-sa 3.0"}

def license_ok(s):
    x=(s or "").lower().strip()
    if any(t in x for t in ("noncommercial","non-commercial","no derivatives","nd 1.0","nd 2.0","nd 3.0","nd 4.0")): return False
    return x in ALLOWED or x.startswith("cc by 4.0") or x.startswith("cc by 3.0") or x.startswith("cc by-sa 4.0") or x.startswith("cc by-sa 3.0")

def candidates(query):
    p={"action":"query","format":"json","generator":"search","gsrsearch":f"filetype:bitmap {query}","gsrnamespace":6,"gsrlimit":20,"prop":"imageinfo","iiprop":"url|extmetadata","iiurlwidth":1400}
    for n in range(4):
        try:
            r=S.get(API,params=p,timeout=35)
            if r.status_code==429: time.sleep(2**n); continue
            r.raise_for_status()
            pages=r.json().get("query",{}).get("pages",{})
            out=[]
            for page in pages.values():
                ii=(page.get("imageinfo") or [{}])[0]; m=ii.get("extmetadata",{})
                lic=m.get("LicenseShortName",{}).get("value","")
                if not license_ok(lic): continue
                url=ii.get("thumburl") or ii.get("url")
                if url: out.append({"title":page.get("title",""),"url":url,"source":ii.get("descriptionurl",""),"license":lic,"artist":m.get("Artist",{}).get("value",""),"credit":m.get("Credit",{}).get("value","")})
            return out
        except requests.RequestException:
            if n==3: raise
            time.sleep(2**n)
    return []

def download(item, media_dir):
    r=S.get(item["url"],timeout=50); r.raise_for_status()
    data=r.content
    if len(data)<5000: raise ValueError("Downloaded image is too small")
    ctype=r.headers.get("Content-Type","").split(";")[0].lower()
    ext=mimetypes.guess_extension(ctype) or Path(item["url"].split("?")[0]).suffix.lower()
    if ext not in (".jpg",".jpeg",".png",".webp"): raise ValueError("Unsupported image format")
    name="medimg_"+hashlib.sha256(data).hexdigest()[:24]+ext
    (media_dir/name).write_bytes(data)
    return name

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("apkg"); ap.add_argument("topics")
    ap.add_argument("-o","--output",default="output_illustrated.apkg")
    a=ap.parse_args()
    topics=json.loads(Path(a.topics).read_text(encoding="utf-8"))
    if not isinstance(topics,list): raise SystemExit("topics.json must contain a JSON list")
    report=[]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); unpack=root/"unpack"; unpack.mkdir(); media=root/"newmedia"; media.mkdir()
        with zipfile.ZipFile(a.apkg) as z: z.extractall(unpack)
        col=unpack/"collection.anki2"; manifest=unpack/"media"
        if not col.exists() or not manifest.exists(): raise SystemExit("Unsupported APKG: collection.anki2 or media manifest missing")
        mm=json.loads(manifest.read_text(encoding="utf-8"))
        con=sqlite3.connect(col)
        rows=con.execute("SELECT id,guid,mid,flds FROM notes").fetchall()
        updates=[]; newmedia=[]
        for t in topics:
            match=(t.get("match") or "").strip(); query=(t.get("query") or "").strip()
            if not match or not query:
                report.append({"match":match,"status":"skipped: match/query missing"}); continue
            hits=[row for row in rows if match.casefold() in row[3].casefold()]
            if len(hits)!=1:
                report.append({"match":match,"status":f"skipped: expected one note, found {len(hits)}"}); continue
            note=hits[0]; fields=note[3].split("\x1f")
            field=t.get("field")
            if field:
                names=[x[0] for x in con.execute("SELECT name FROM fields WHERE ntid=? ORDER BY ord",(note[2],))]
                if field not in names:
                    report.append({"match":match,"status":f"skipped: field {field} not found"}); continue
                idx=names.index(field)
            else: idx=0
            found=candidates(query)
            if not found:
                report.append({"match":match,"status":"no image with accepted license"}); continue
            item=found[0]
            try: filename=download(item,media)
            except Exception as e:
                report.append({"match":match,"status":f"download failed: {e}"}); continue
            while len(fields)<=idx: fields.append("")
            credit=f'<br><img src="{filename}"><br><small>Source: {item["title"]} | {item["license"]} | {item["source"]}</small>'
            fields[idx]+=credit
            updates.append(("\x1f".join(fields),int(time.time()),note[0]))
            newmedia.append((filename,item))
            report.append({"match":match,"status":"added","image":filename,"title":item["title"],"license":item["license"],"source":item["source"]})
        for flds,mod,nid in updates:
            con.execute("UPDATE notes SET flds=?,mod=? WHERE id=?",(flds,mod,nid))
        con.commit()
        check=con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
        if check!="ok": raise RuntimeError("SQLite integrity check failed: "+str(check))
        for i,(filename,item) in enumerate(newmedia):
            key=str(len(mm)); mm[key]=filename
            shutil.copy2(media/filename,unpack/key)
        manifest.write_text(json.dumps(mm,ensure_ascii=False),encoding="utf-8")
        out=Path(a.output)
        with zipfile.ZipFile(a.apkg) as src, zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as dst:
            for info in src.infolist():
                if info.filename in ("collection.anki2","media"): continue
                dst.writestr(info,src.read(info.filename))
            dst.write(col,"collection.anki2"); dst.write(manifest,"media")
            for key in mm:
                if (unpack/key).exists(): dst.write(unpack/key,key)
        Path(str(out)+".report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Output: {a.output}; modified notes: {len(updates)}; image candidates added: {len(newmedia)}")
    print(f"Report: {a.output}.report.json")
if __name__=="__main__": main()

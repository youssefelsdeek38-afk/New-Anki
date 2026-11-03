#!/usr/bin/env python3
"""Enrich an APKG with openly licensed Wikimedia Commons images; show images on the answer side."""
import argparse, hashlib, json, mimetypes, os, re, shutil, sqlite3, tempfile, time, zipfile
from pathlib import Path
import requests

API = "https://commons.wikimedia.org/w/api.php"
S = requests.Session()
S.headers.update({"User-Agent": "NewAnkiMedicalImagePipeline/2.0 (educational flashcard project)"})

def license_ok(value):
    x = re.sub(r"\\s+", " ", (value or "").lower()).strip()
    if any(term in x for term in ("noncommercial", "non-commercial", "no derivatives", "cc by-nc", "cc by-nd")):
        return False
    return x in {"cc0", "public domain", "cc by 4.0", "cc by 3.0", "cc by-sa 4.0", "cc by-sa 3.0"}

def candidates(query):
    params = {"action":"query","format":"json","generator":"search",
              "gsrsearch":f"filetype:bitmap {query}","gsrnamespace":6,"gsrlimit":30,
              "prop":"imageinfo","iiprop":"url|extmetadata","iiurlwidth":1500}
    response = S.get(API, params=params, timeout=45)
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    result = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if not license_ok(lic):
            continue
        url = info.get("thumburl") or info.get("url")
        if url:
            result.append({"title":page.get("title",""), "url":url,
                           "source":info.get("descriptionurl",""), "license":lic,
                           "artist":meta.get("Artist",{}).get("value",""),
                           "credit":meta.get("Credit",{}).get("value","")})
    return result

def download(item, media_dir):
    r = S.get(item["url"], timeout=60)
    r.raise_for_status()
    data = r.content
    ctype = r.headers.get("Content-Type","").split(";")[0].lower()
    ext = mimetypes.guess_extension(ctype) or Path(item["url"].split("?")[0]).suffix.lower()
    if len(data) < 5000 or ext not in (".jpg",".jpeg",".png",".webp"):
        raise ValueError("Invalid or unsupported image response")
    name = "commons_" + hashlib.sha256(data).hexdigest()[:20] + ext
    (media_dir/name).write_bytes(data)
    return name

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("apkg"); ap.add_argument("topics")
    ap.add_argument("-o","--output",default="CVS_Anki_Internet_Illustrated.apkg")
    args = ap.parse_args()
    topics = json.loads(Path(args.topics).read_text(encoding="utf-8"))
    report = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); unpack = root/"unpack"; unpack.mkdir()
        media = root/"newmedia"; media.mkdir()
        with zipfile.ZipFile(args.apkg) as z: z.extractall(unpack)
        col = unpack/"collection.anki2"; manifest = unpack/"media"
        if not col.exists() or not manifest.exists():
            raise SystemExit("Unsupported APKG format")
        mm = json.loads(manifest.read_text(encoding="utf-8"))
        con = sqlite3.connect(col)
        models = json.loads(con.execute("SELECT models FROM col").fetchone()[0])
        rows = con.execute("SELECT id,guid,mid,flds FROM notes").fetchall()
        updates = []; newmedia = []
        for topic in topics:
            match = (topic.get("match") or "").strip()
            query = (topic.get("query") or "").strip()
            hits = [row for row in rows if match and match.casefold() in row[3].casefold()]
            if len(hits) != 1:
                report.append({"match":match,"status":f"skipped: matched {len(hits)} notes"}); continue
            note = hits[0]; fields = note[3].split("\x1f")
            model = models.get(str(note[2]), {})
            names = [f.get("name","") for f in model.get("flds",[])]
            if "Image" not in names or not query:
                report.append({"match":match,"status":"skipped: Image field or query missing"}); continue
            idx = names.index("Image")
            try:
                options = candidates(query)
                if not options: raise ValueError("No suitable openly licensed Commons image found")
                item = options[0]
                filename = download(item, media)
                credit = (f'<img src="{filename}"><br><small>Image: {item["title"]} | '
                          f'{item["license"]} | <a href="{item["source"]}">Wikimedia Commons</a></small>')
                fields[idx] = credit
                updates.append(( "\x1f".join(fields), int(time.time()), note[0]))
                newmedia.append((filename,item))
                report.append({"match":match,"status":"added","image":filename,
                               "title":item["title"],"license":item["license"],"source":item["source"]})
            except Exception as exc:
                report.append({"match":match,"status":f"failed: {exc}"})
        # Move Image rendering from question to answer. Keep the Image field and all note/card IDs.
        for model in models.values():
            for template in model.get("tmpls",[]):
                qfmt = template.get("qfmt","")
                qfmt = re.sub(r'<div class="imgbox">\\s*{{Image}}\\s*</div>', '', qfmt, flags=re.I)
                template["qfmt"] = qfmt
                afmt = template.get("afmt","")
                if "{{#Image}}" not in afmt:
                    template["afmt"] = afmt + '<br>{{#Image}}<div class="answer-image">{{Image}}</div>{{/Image}}'
        con.execute("UPDATE col SET models=?", (json.dumps(models,ensure_ascii=False),))
        for flds, mod, nid in updates:
            con.execute("UPDATE notes SET flds=?,mod=? WHERE id=?", (flds,mod,nid))
        con.commit()
        check = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
        if check != "ok": raise RuntimeError("SQLite integrity check failed")
        # Add media entries using unused numeric keys, never by assuming len(manifest) is safe.
        used = {int(k) for k in mm if str(k).isdigit()}
        next_key = max(used, default=-1) + 1
        for filename, item in newmedia:
            while str(next_key) in mm: next_key += 1
            mm[str(next_key)] = filename
            shutil.copy2(media/filename, unpack/str(next_key))
            next_key += 1
        manifest.write_text(json.dumps(mm,ensure_ascii=False),encoding="utf-8")
        output = Path(args.output)
        with zipfile.ZipFile(args.apkg) as src, zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as dst:
            for info in src.infolist():
                if info.filename in ("collection.anki2","media"): continue
                dst.writestr(info,src.read(info.filename))
            dst.write(col,"collection.anki2"); dst.write(manifest,"media")
            for key in mm:
                if (unpack/key).exists(): dst.write(unpack/key,key)
        Path(str(output)+".report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Output: {args.output}; cards updated: {len(updates)}; internet images embedded: {len(newmedia)}")
    print(f"Report: {args.output}.report.json")

if __name__ == "__main__":
    main()

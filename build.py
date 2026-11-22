#!/usr/bin/env python3
"""Build the public now—ness site from NOWNESS markdown issues.

Usage: python3 build.py <NOWNESS dir> <output dir>
Reads Archive/YYYY-MM-DD.md (+ optional _system/site-YYYY-MM-DD.json for one-liners,
key numbers and rights-cleared images). Writes index.html, YYYY-MM-DD/index.html,
archive/index.html and copies style.css. Standard library only.
"""
import html, json, os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SECTION_EN = {"AI郵報精選": "AI Post", "股市新手解讀": "Market", "國際與資訊戰": "World", "國際": "World",
              "政治與世代": "Politics", "資料與科技權力": "Tech", "科技": "Tech", "AI與數學": "AI & Math",
              "科學選讀": "Science", "科學": "Science", "歷史與文化": "Culture", "工具與圖像": "Tools",
              "工具": "Tools", "圖像": "Image"}
SKIP_SECTIONS = {"今日目錄", "本期涵蓋"}
PRIVATE = re.compile(r"[^。；\n]*DIARY[^。；\n]*[。；]?")
ESC = html.escape


def inline(s):
    """Markdown inline subset -> HTML. Drops obsidian:// and same-page anchor links, keeps their text."""
    out, pos = [], 0
    for m in re.finditer(r"\[([^\]]+)\]\(<?([^)>\s]+)>?\)|\*\*([^*]+)\*\*", s):
        out.append(ESC(s[pos:m.start()]))
        if m.group(3):
            out.append(f"<b>{ESC(m.group(3))}</b>")
        else:
            text, url = m.group(1), m.group(2)
            if url.startswith(("http://", "https://")):
                out.append(f'<a href="{ESC(url)}" rel="noopener">{ESC(text)}</a>')
            else:
                out.append(ESC(text))
        pos = m.end()
    out.append(ESC(s[pos:]))
    return "".join(out)


def plain(s):
    return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s).replace("**", "").strip()


def parse_issue(path):
    text = PRIVATE.sub("", open(path, encoding="utf-8").read())
    date = os.path.basename(path)[:10]
    body = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    h1 = re.search(r"^# (.+)$", body, re.M)
    title = h1.group(1).split("｜", 1)[-1].strip() if h1 else date
    brief = ""
    ab = re.search(r"^> \[!abstract\][^\n]*\n((?:>.*\n?)+)", body, re.M)
    if ab:
        lines = [l[1:].strip() for l in ab.group(1).splitlines()]
        brief = next((l for l in lines if l and not l.startswith("**") and "本期" not in l[:4]), lines[0] if lines else "")
        brief = re.split(r"[；。]", plain(brief))[0]  # old issues have long briefs; site json brief overrides
        brief = brief if len(brief) <= 70 else brief[:68] + "…"
    sections, cur_sec, cur = [], None, None
    coverage = []
    for line in body.splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
            cur_sec = None if name in SKIP_SECTIONS else {"name": name, "stories": []}
            if cur_sec:
                sections.append(cur_sec)
            cur = None
            coverage_mode = name == "本期涵蓋"
            continue
        if line.startswith("### ") and cur_sec is not None:
            cur = {"title": line[4:].strip(), "lines": []}
            cur_sec["stories"].append(cur)
            continue
        if cur is not None:
            cur["lines"].append(line)
        elif locals().get("coverage_mode") and line.startswith(">"):
            coverage.append(line.lstrip("> ").strip())
    for sec in sections:
        for st in sec["stories"]:
            finish_story(st)
    sections = [s for s in sections if s["stories"]]
    return {"date": date, "title": title, "brief": brief, "sections": sections,
            "coverage": [c for c in coverage if c and not c.startswith("[!")]}


def finish_story(st):
    paras, details, sources, oneliner = [], [], "", None
    block = None
    for raw in st["lines"]:
        line = raw.rstrip()
        m = re.match(r"^> \[!(\w+)\]-?\s*(.*)$", line)
        if m:
            block = {"title": m.group(2) or m.group(1), "lines": []}
            details.append(block)
            continue
        if line.startswith(">") and block is not None:
            block["lines"].append(line.lstrip(">").strip())
            continue
        block = None
        s = line.strip()
        if not s or s.startswith("[← ") or s.startswith("[↑") or s.startswith("[Archive]"):
            continue
        if s.startswith("來源："):
            sources = s[3:].strip()
            continue
        if s.startswith("一句話：") and oneliner is None:
            oneliner = s[4:].strip()
            continue
        if s.startswith("- "):
            paras.append(("li", s[2:]))
        else:
            paras.append(("p", s))
    st["oneliner_real"] = oneliner is not None
    if oneliner is None and paras:
        first = plain(paras[0][1])
        cut = re.split(r"(?<=[。！？])", first)
        oneliner = cut[0] if cut and len(cut[0]) <= 90 else first[:80] + "…"
    st.update(paras=paras, details=[d for d in details if d["lines"]], sources=sources, oneliner=oneliner)
    del st["lines"]


def apply_site_json(issue, nowness):
    """Merge the routine's site json, then hand-picked images/<date>.json in this repo (wins for images)."""
    for p in (os.path.join(nowness, "_system", f"site-{issue['date']}.json"),
              os.path.join(HERE, "images", f"{issue['date']}.json")):
        if os.path.exists(p):
            try:
                merge_items(issue, json.load(open(p, encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                pass


def merge_items(issue, data):
    by = {}
    for it in data.get("items", []):
        for k in (it.get("anchor"), it.get("title")):
            if k:
                by[k.strip()] = it
    for sec in issue["sections"]:
        for st in sec["stories"]:
            it = by.get(st["title"])
            if not it:
                continue
            if it.get("oneliner"):
                st["oneliner"], st["oneliner_real"] = it["oneliner"], True
            if "key_number" in it:
                st["key_number"] = it["key_number"]
            img = it.get("image")
            if isinstance(img, dict) and str(img.get("url", "")).startswith("https://"):
                st["image"] = img
    if data.get("brief"):
        issue["brief"] = data["brief"]


def slug(s):
    return re.sub(r"[^\w一-鿿-]+", "-", s).strip("-")[:60] or "s"


def head(title, depth):
    up = "../" * depth
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{ESC(title)}</title><link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Oxanium:wght@300;400;500&family=Chiron+Hei+HK:wght@400;500;600&display=swap">
<link rel="stylesheet" href="{up}style.css"></head><body><div class="wrap">"""


def mast(date, depth, stamp=""):
    up = "../" * depth
    d = date.split("-")
    return (f'<header class="mast"><a class="mark" href="{up}index.html">now<i>—</i>ness</a>'
            f'<div class="stamp">{d[2]}.{d[1]}.{d[0]}<span>{ESC(stamp)}</span></div></header>')


def media(st, big_ok=True):
    """Image card if rights-cleared image exists, else blank typographic card."""
    kn = st.get("key_number")
    img = st.get("image")
    if img:
        bignum = f'<p class="big">{ESC(kn)}</p>' if kn and big_ok else ""
        credit = ESC(" · ".join(x for x in (img.get("credit"), img.get("license")) if x))
        page = img.get("page")
        credit_html = f'<a href="{ESC(page)}" rel="noopener">{credit}</a>' if page else credit
        return (f'<figure class="photo"><img src="{ESC(img["url"])}" alt="" loading="lazy">'
                f'<figcaption class="on">{bignum}<h3>{ESC(st["title"])}</h3></figcaption></figure>'
                f'<p class="credit">Photo: {credit_html}</p>')
    bignum = f'<p class="big">{ESC(kn)}</p>' if kn and big_ok else ""
    return f'<div class="blank">{bignum}<h3>{ESC(st["title"])}</h3></div>'


def render_index(issue, total_issues):
    d = issue["date"]
    n = sum(len(s["stories"]) for s in issue["sections"])
    out = [head("now—ness", 0), mast(d, 0, f"{n} 則"),
           f'<div class="today"><p class="lbl">Today, in one line</p><h1>{ESC(issue["title"])}</h1>']
    if issue["brief"]:
        out.append(f'<p class="brief">{inline(issue["brief"])}</p>')
    out.append('<nav class="index" aria-label="分區">' + "".join(
        f'<a href="#{slug(s["name"])}">{ESC(s["name"])}<sup>{len(s["stories"])}</sup></a>' for s in issue["sections"]) + "</nav></div>")
    for s in issue["sections"]:
        en = SECTION_EN.get(s["name"], "")
        out.append(f'<section id="{slug(s["name"])}"><div class="sh"><h2>{ESC(en)}<span>{ESC(s["name"])}</span></h2>'
                   f'<span class="count">{len(s["stories"])} / {n}</span></div>')
        if s["name"] == "股市新手解讀":
            out.append('<p class="disc">新聞解讀，不是投資建議。</p>')
        for i, st in enumerate(s["stories"]):
            link = f'{d}/index.html#{slug(st["title"])}'
            if i == 0:
                out.append(f'<article class="story">{media(st)}<p class="one">{ESC(st["oneliner"] or "")}</p>'
                           f'<div class="links"><a href="{link}"><u>全文與來源</u></a></div></article>')
            else:
                thumb = (f'<img class="thumb" src="{ESC(st["image"]["url"])}" alt="" loading="lazy">' if st.get("image") else "")
                out.append(f'<a class="short{"" if thumb else " noimg"}" href="{link}">{thumb}<div><h4>{ESC(st["title"])}</h4>'
                           f'<p>{ESC(st["oneliner"] or "")}</p></div></a>')
        out.append("</section>")
    out.append(f'<footer><a class="mark" href="index.html">now<i>—</i>ness</a>'
               f'<a href="{d}/index.html">本期全文</a> · <a href="archive/index.html">過去 {total_issues} 期</a></footer></div></body></html>')
    return "".join(out)


def render_issue(issue, prev_d, next_d):
    d = issue["date"]
    out = [head(f'{d} — now—ness', 1), mast(d, 1),
           f'<div class="today"><p class="lbl">Issue {ESC(d)}</p><h1>{ESC(issue["title"])}</h1>']
    if issue["brief"]:
        out.append(f'<p class="brief">{inline(issue["brief"])}</p>')
    out.append('<nav class="index" aria-label="分區">' + "".join(
        f'<a href="#{slug(s["name"])}">{ESC(s["name"])}<sup>{len(s["stories"])}</sup></a>' for s in issue["sections"]) + "</nav></div>")
    for s in issue["sections"]:
        en = SECTION_EN.get(s["name"], "")
        out.append(f'<section id="{slug(s["name"])}"><div class="sh"><h2>{ESC(en)}<span>{ESC(s["name"])}</span></h2></div>')
        if s["name"] == "股市新手解讀":
            out.append('<p class="disc">新聞解讀，不是投資建議。</p>')
        for st in s["stories"]:
            out.append(f'<article class="story full" id="{slug(st["title"])}">{media(st)}')
            if st.get("oneliner_real"):
                out.append(f'<p class="one">{ESC(st["oneliner"])}</p>')
            body, in_list = [], False
            for kind, txt in st["paras"]:
                if kind == "li" and not in_list:
                    body.append("<ul>"); in_list = True
                if kind != "li" and in_list:
                    body.append("</ul>"); in_list = False
                body.append(f"<li>{inline(txt)}</li>" if kind == "li" else f"<p>{inline(txt)}</p>")
            if in_list:
                body.append("</ul>")
            out.append(f'<div class="body">{"".join(body)}</div>')
            if st["sources"]:
                out.append(f'<p class="src"><span>來源</span>{inline(st["sources"])}</p>')
            for dt in st["details"]:
                out.append(f'<details><summary>{ESC(plain(dt["title"]))}</summary>'
                           + "".join(f"<p>{inline(l)}</p>" for l in dt["lines"] if l) + "</details>")
            out.append("</article>")
        out.append("</section>")
    if issue["coverage"]:
        out.append('<details class="cov"><summary>本期涵蓋與查核</summary>'
                   + "".join(f"<p>{inline(c)}</p>" for c in issue["coverage"]) + "</details>")
    nav = []
    if prev_d:
        nav.append(f'<a href="../{prev_d}/index.html">← {prev_d}</a>')
    nav.append('<a href="../archive/index.html">所有期數</a>')
    if next_d:
        nav.append(f'<a href="../{next_d}/index.html">{next_d} →</a>')
    out.append(f'<footer class="pager">{"".join(nav)}</footer></div></body></html>')
    return "".join(out)


def render_archive(issues):
    out = [head("所有期數 — now—ness", 1), mast(issues[0]["date"], 1),
           '<div class="today"><p class="lbl">Archive</p><h1>所有期數</h1></div><section>']
    for it in issues:
        out.append(f'<a class="short noimg" href="../{it["date"]}/index.html"><div><h4>{ESC(it["date"])}</h4>'
                   f'<p>{ESC(it["title"])}</p></div></a>')
    out.append("</section></div></body></html>")
    return "".join(out)


def write(path, s):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(s)


def main(nowness, outdir):
    arch = os.path.join(nowness, "Archive")
    files = sorted(f for f in os.listdir(arch) if re.match(r"\d{4}-\d{2}-\d{2}\.md$", f))
    issues = []
    for f in files:
        it = parse_issue(os.path.join(arch, f))
        apply_site_json(it, nowness)
        if it["sections"]:
            issues.append(it)
    assert issues, "no issues parsed"
    issues.sort(key=lambda x: x["date"], reverse=True)
    for i, it in enumerate(issues):
        prev_d = issues[i + 1]["date"] if i + 1 < len(issues) else None
        next_d = issues[i - 1]["date"] if i > 0 else None
        write(os.path.join(outdir, it["date"], "index.html"), render_issue(it, prev_d, next_d))
    write(os.path.join(outdir, "index.html"), render_index(issues[0], len(issues)))
    write(os.path.join(outdir, "archive", "index.html"), render_archive(issues))
    css = os.path.join(outdir, "style.css")
    if not os.path.exists(css) or not os.path.samefile(os.path.join(HERE, "style.css"), css):
        shutil.copy(os.path.join(HERE, "style.css"), css)
    open(os.path.join(outdir, ".nojekyll"), "w").close()
    print(f"built {len(issues)} issues, latest {issues[0]['date']}, "
          f"{sum(len(s['stories']) for s in issues[0]['sections'])} stories")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])

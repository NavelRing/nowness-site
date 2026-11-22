#!/bin/sh
# Self-check for build.py: one synthetic issue in the new format (一句話 + site json with image and key number).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/Archive" "$T/_system"
printf -- '---\ndate: 2099-01-01\n---\n# 2099.01.01｜測試\n\n> [!abstract] 今日先讀\n> 測試一句；第二句\n\n## 股市新手解讀\n\n> [!info] 股市新手解讀\n\n### 輝達跌了\n\n一句話：輝達單日大跌。\n\n第一段內容，含 DIARY 的句子會被移除。\n\n來源：[CNBC](https://example.com/a)\n\n> [!note]- 查證與待追蹤\n> 已核對。\n' > "$T/Archive/2099-01-01.md"
printf '{"date":"2099-01-01","brief":"網站用的一句","items":[{"title":"輝達跌了","anchor":"輝達跌了","oneliner":"JSON一句話","key_number":"−14%%","image":{"url":"https://upload.wikimedia.org/x.jpg","credit":"Someone","license":"CC BY 4.0","page":"https://commons.wikimedia.org/wiki/File:x.jpg"}}]}' > "$T/_system/site-2099-01-01.json"
python3 "$HERE/build.py" "$T" "$T/out" >/dev/null
python3 - "$T/out" <<'E'
import sys; o = sys.argv[1]
i = open(o + '/index.html').read(); p = open(o + '/2099-01-01/index.html').read()
assert '網站用的一句' in i and 'JSON一句話' in i and '−14%' in i, 'index text'
assert 'upload.wikimedia.org/x.jpg' in i and 'CC BY 4.0' in i, 'image + credit'
assert '新聞解讀，不是投資建議' in i, 'market disclaimer'
assert p.count('class="one"') == 1 and '第一段內容' not in p and 'DIARY' not in p, 'issue page / privacy filter'
assert '<details>' in p, 'collapsed notes'
print('selftest ok')
E

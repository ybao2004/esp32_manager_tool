import urllib.request
import json
import re

url = "https://github.com/microsoft/fluentui-system-icons/tree/main/assets"
try:
    html = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=10).read().decode('utf-8')
    m = re.search(r'<script\s+type="application/json"\s+data-target="react-app\.embeddedData">\s*({.*?})\s*</script>', html, re.DOTALL)
    if m:
        data = json.loads(m.group(1))
        items = data.get("payload", {}).get("tree", {}).get("items", [])
        names = [it.get("name") for it in items]
        print("Total items:", len(names))
        print("Matches containing 'wi':", [n for n in names if 'wi' in n.lower()])
    else:
        print("No react embedded data found")
except Exception as e:
    print("Error:", e)

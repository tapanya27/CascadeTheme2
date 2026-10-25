import re
import urllib.request

url = "https://github.com/yashveeeeeeer/india-geodata/releases/expanded_assets/healthcare%2Ffacilities"
req = urllib.request.Request(url, headers={"User-Agent": "Critical1"})
html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
files = re.findall(
    r'href="(/yashveeeeeeer/india-geodata/releases/download/[^"]+)"', html
)
print("download hrefs", len(files))
for f in files:
    print(f)

wp = "https://data.worldpop.org/GIS/Population_Density/Global_2000_2020_1km/2020/IND/ind_pd_2020_1km.tif"
req2 = urllib.request.Request(wp, method="HEAD", headers={"User-Agent": "Critical1"})
try:
    r = urllib.request.urlopen(req2, timeout=60)
    print("worldpop", r.status, r.headers.get("Content-Length"))
except Exception as e:
    print("worldpop fail", e)

hdx = (
    "https://data.humdata.org/dataset/fb4f6952-3a04-4be7-a74f-489d5197fb74/"
    "resource/8046d95f-664e-48b2-af97-27d0ac5be900/download/ind_pd_2020_1km.tif"
)
req3 = urllib.request.Request(hdx, method="HEAD", headers={"User-Agent": "Critical1"})
try:
    r = urllib.request.urlopen(req3, timeout=60)
    print("hdx", r.status, r.headers.get("Content-Length"), r.geturl())
except Exception as e:
    print("hdx fail", e)

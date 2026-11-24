"""
Hava Durumu + Giyim Önerisi Web Uygulaması
Kurulum : pip install flask requests
Çalıştır: python hava_app.py   ->  http://127.0.0.1:5000
Veri    : Open-Meteo (ücretsiz, API anahtarı gerekmez)
"""
import math
import os
import time
from urllib.parse import quote
import requests
from flask import Flask, jsonify, request, Response

app = Flask(__name__)
# Yayına alınca kendi alan adını yaz: SITE_URL=https://siteadin.com (ortam değişkeni)
SITE_URL = os.environ.get("SITE_URL", "http://127.0.0.1:5000").rstrip("/")
_cache = {}  # basit önbellek: aynı konuma 10 dk boyunca tekrar istek atmaz

KODLAR = {
    0: ("Açık", "☀️"), 1: ("Çoğunlukla açık", "🌤️"), 2: ("Parçalı bulutlu", "⛅"),
    3: ("Kapalı", "☁️"), 45: ("Sisli", "🌫️"), 48: ("Kırağılı sis", "🌫️"),
    51: ("Hafif çisenti", "🌦️"), 53: ("Çisenti", "🌦️"), 55: ("Yoğun çisenti", "🌧️"),
    61: ("Hafif yağmur", "🌦️"), 63: ("Yağmur", "🌧️"), 65: ("Şiddetli yağmur", "🌧️"),
    71: ("Hafif kar", "🌨️"), 73: ("Kar", "❄️"), 75: ("Yoğun kar", "❄️"), 77: ("Kar taneleri", "❄️"),
    80: ("Hafif sağanak", "🌦️"), 81: ("Sağanak", "🌧️"), 82: ("Şiddetli sağanak", "⛈️"),
    85: ("Kar sağanağı", "🌨️"), 86: ("Yoğun kar sağanağı", "🌨️"),
    95: ("Gök gürültülü fırtına", "⛈️"), 96: ("Dolu ile fırtına", "⛈️"), 99: ("Şiddetli dolu", "⛈️"),
}
KAR = {71, 73, 75, 77, 85, 86}
YAGMUR = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}


def giyim_onerisi(hissedilen, yagis, ruzgar, uv, kod):
    """Hissedilen sıcaklık, yağış ihtimali, rüzgar, UV ve hava koduna göre giyim önerisi üretir."""
    if hissedilen <= 0:
        baslik, tip, emoji = "ÇOK KALIN GİYİN", "kalin", "🥶"
        parcalar = ["Kalın mont", "Termal içlik", "Kazak", "Bere, atkı, eldiven", "Kalın pantolon", "Bot"]
    elif hissedilen <= 9:
        baslik, tip, emoji = "KALIN GİYİN", "kalin", "🧥"
        parcalar = ["Mont veya kaban", "Kazak", "Uzun pantolon", "Bere ve atkı"]
    elif hissedilen <= 16:
        baslik, tip, emoji = "ORTA KALINLIKTA GİYİN", "orta", "🧣"
        parcalar = ["Ceket veya hırka", "Uzun kollu üst", "Uzun pantolon"]
    elif hissedilen <= 22:
        baslik, tip, emoji = "HAFİF KATMANLI GİYİN", "orta", "👕"
        parcalar = ["İnce sweatshirt veya gömlek", "Uzun pantolon", "Yanına ince bir ceket al"]
    elif hissedilen <= 28:
        baslik, tip, emoji = "İNCE GİYİN", "ince", "😎"
        parcalar = ["Tişört", "İnce pantolon veya şort", "Rahat ayakkabı"]
    else:
        baslik, tip, emoji = "ÇOK İNCE GİYİN", "ince", "🥵"
        parcalar = ["Pamuklu, açık renkli tişört", "Şort", "Sandalet", "Bol su iç"]

    ekstra = []
    if kod in KAR:
        ekstra.append("❄️ Kar var: su geçirmez bot ve eldiven tak")
    elif kod in YAGMUR or yagis >= 40:
        ekstra.append("☔ Şemsiye veya yağmurluk al")
    if kod in (95, 96, 99):
        ekstra.append("⚡ Fırtına riski: mümkünse dışarı çıkma")
    if ruzgar >= 30:
        ekstra.append("💨 Rüzgar sert: rüzgarlık giy")
    if uv >= 6:
        ekstra.append("🕶️ UV yüksek: güneş kremi, gözlük ve şapka kullan")
    if tip == "ince" and hissedilen > 28:
        ekstra.append("💧 Sıcak var: gün içinde bol su iç")
    return {"baslik": baslik, "tip": tip, "emoji": emoji, "parcalar": parcalar, "ekstra": ekstra}


def kisa_etiket(t):
    return "Kalın" if t <= 9 else "Orta" if t <= 22 else "İnce"


@app.route("/api/ara")
def ara():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    try:
        r = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": q, "count": 6, "language": "tr"}, timeout=10,
        )
        return jsonify(r.json().get("results", []))
    except requests.RequestException:
        return jsonify([])


@app.route("/api/hava")
def hava():
    try:
        lat, lon = float(request.args["lat"]), float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"hata": "Geçersiz konum"}), 400

    anahtar = (round(lat, 2), round(lon, 2))
    if anahtar in _cache and time.time() - _cache[anahtar][0] < 600:
        return jsonify(_cache[anahtar][1])

    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 7,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code,is_day",
                "hourly": "temperature_2m,precipitation_probability,precipitation",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,uv_index_max",
            },
            timeout=10,
        )
        r.raise_for_status()
        v = r.json()
    except requests.RequestException:
        return jsonify({"hata": "Hava durumu servisine ulaşılamadı"}), 502

    c, d = v["current"], v["daily"]
    ad, emoji = KODLAR.get(c["weather_code"], ("Bilinmiyor", "🌡️"))
    yagis = d["precipitation_probability_max"][0] or 0
    uv = d["uv_index_max"][0] or 0

    gunler = []
    for i in range(7):
        gad, gemoji = KODLAR.get(d["weather_code"][i], ("", "🌡️"))
        ort = (d["temperature_2m_max"][i] + d["temperature_2m_min"][i]) / 2
        gunler.append({
            "tarih": d["time"][i], "emoji": gemoji, "durum": gad,
            "max": round(d["temperature_2m_max"][i]), "min": round(d["temperature_2m_min"][i]),
            "yagis": d["precipitation_probability_max"][i] or 0, "giyim": kisa_etiket(ort),
        })

    saatlik = {}
    hv = v["hourly"]
    for i, t in enumerate(hv["time"]):
        saatlik.setdefault(t[:10], []).append({
            "saat": t[11:16],
            "yagis": hv["precipitation_probability"][i] or 0,
            "mm": hv["precipitation"][i] or 0,
            "sicaklik": round(hv["temperature_2m"][i]),
        })

    sonuc = {
        "sicaklik": round(c["temperature_2m"]), "hissedilen": round(c["apparent_temperature"]),
        "nem": c["relative_humidity_2m"], "ruzgar": round(c["wind_speed_10m"]),
        "durum": ad, "emoji": emoji, "gece": c["is_day"] == 0, "kod": c["weather_code"],
        "yagis": yagis, "uv": round(uv, 1),
        "oneri": giyim_onerisi(c["apparent_temperature"], yagis, c["wind_speed_10m"], uv, c["weather_code"]),
        "gunler": gunler, "saatlik": saatlik, "saat": c["time"][11:13],
    }
    _cache[anahtar] = (time.time(), sonuc)
    return jsonify(sonuc)


_mekan_cache = {}
_konum_cache = {}
UA = {"User-Agent": "HavaApp/1.0 (ogrenme projesi)"}


def mesafe_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


@app.route("/api/mekan")
def mekan():
    """Konuma YAKIN ve BİLİNEN yeri seçer: puan = okunma sayısı / (1 + (mesafe/2 km)^2)."""
    try:
        lat, lon = float(request.args["lat"]), float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify(None)

    anahtar = (round(lat, 2), round(lon, 2))
    if anahtar in _mekan_cache:
        return jsonify(_mekan_cache[anahtar])

    en_iyi, en_puan = None, -1
    for dil in ("tr", "en"):
        try:
            r = requests.get(
                f"https://{dil}.wikipedia.org/w/api.php",
                params={
                    "action": "query", "format": "json", "generator": "geosearch",
                    "ggscoord": f"{lat}|{lon}", "ggsradius": 10000, "ggslimit": 50,
                    "prop": "pageimages|pageviews|coordinates", "piprop": "thumbnail",
                    "pithumbsize": 1600, "pilimit": 50, "pvipdays": 30, "colimit": 50,
                },
                headers=UA, timeout=10,
            )
            sayfalar = r.json().get("query", {}).get("pages", {})
        except (requests.RequestException, ValueError):
            continue
        for s in sayfalar.values():
            th, co = s.get("thumbnail"), s.get("coordinates")
            if not th or not co or ".svg" in th["source"].lower():
                continue
            km = mesafe_km(lat, lon, co[0]["lat"], co[0]["lon"])
            gorunum = sum(v or 0 for v in (s.get("pageviews") or {}).values())
            puan = gorunum / (1 + (km / 2) ** 2)
            if dil == "tr":
                puan *= 3  # Türkçe sayfalar daha az okunur, dengele
            if th["width"] < th["height"]:
                puan *= 0.3  # yatay fotoğrafları tercih et
            if puan > en_puan:
                en_iyi, en_puan = (s, dil, km), puan

    sonuc = None
    if en_iyi:
        s, dil, km = en_iyi
        sonuc = {
            "baslik": s["title"], "resim": s["thumbnail"]["source"], "mesafe": round(km, 1),
            "link": f"https://{dil}.wikipedia.org/wiki/" + quote(s["title"].replace(" ", "_")),
        }
    _mekan_cache[anahtar] = sonuc
    return jsonify(sonuc)


@app.route("/api/konum")
def konum():
    """Koordinattan ilçe ve il adını bulur (OpenStreetMap Nominatim)."""
    try:
        lat, lon = float(request.args["lat"]), float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"ad": ""})

    anahtar = (round(lat, 3), round(lon, 3))
    if anahtar in _konum_cache:
        return jsonify(_konum_cache[anahtar])

    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 12, "accept-language": "tr"},
            headers=UA, timeout=10,
        )
        a = r.json().get("address", {})
    except (requests.RequestException, ValueError):
        return jsonify({"ad": ""})

    il = a.get("province") or a.get("state") or a.get("city") or ""
    ilce = (a.get("county") or a.get("town") or a.get("city_district")
            or a.get("suburb") or a.get("village") or a.get("city") or "")
    parcalar = [x for x in (ilce, il) if x]
    if len(parcalar) == 2 and parcalar[0] == parcalar[1]:
        parcalar = parcalar[:1]
    sonuc = {"ad": ", ".join(parcalar), "il": il, "ilce": ilce}
    _konum_cache[anahtar] = sonuc
    return jsonify(sonuc)


@app.route("/robots.txt")
def robots():
    metin = f"User-agent: *\nAllow: /\nDisallow: /api/\n\nSitemap: {SITE_URL}/sitemap.xml\n"
    return Response(metin, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           f"<url><loc>{SITE_URL}/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>"
           "</urlset>")
    return Response(xml, mimetype="application/xml")


@app.route("/")
def ana_sayfa():
    return Response(HTML.replace("__SITE__", SITE_URL), mimetype="text/html")


HTML = r"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hava Durumu ve Giyim Önerisi | Saatlik Yağış, 7 Günlük Tahmin</title>
<meta name="description" content="Şehrine göre anlık hava durumu, saatlik yağış tahmini, 7 günlük tahmin ve ne giyeceğine dair giyim önerisi. Ücretsiz hava durumu uygulaması.">
<meta name="keywords" content="hava durumu, saatlik hava durumu, yağış tahmini, giyim önerisi, ne giyeceğim, 7 günlük hava durumu">
<link rel="canonical" href="__SITE__/">
<meta name="google-site-verification" content="WvC4nrYoly4ksP66FpWEhkJl3Ud_SDObnYR9pgt-FzU" />
<meta property="og:type" content="website">
<meta property="og:title" content="Hava Durumu ve Giyim Önerisi">
<meta property="og:description" content="Anlık hava, saatlik yağış, 7 günlük tahmin ve ne giyeceğin tek sayfada.">
<meta property="og:url" content="__SITE__/">
<meta name="theme-color" content="#0f2027">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"WebApplication","name":"Hava Durumu ve Giyim Önerisi",
 "url":"__SITE__/","applicationCategory":"WeatherApplication","operatingSystem":"Web",
 "inLanguage":"tr","offers":{"@type":"Offer","price":"0","priceCurrency":"TRY"}}
</script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,Segoe UI,sans-serif;color:#fff;min-height:100vh;padding:24px 16px;
 background:linear-gradient(135deg,#2c5364,#0f2027);transition:background .6s}
body.gunes{background:linear-gradient(135deg,#f7971e,#ff5e62)}
body.bulut{background:linear-gradient(135deg,#606c88,#3f4c6b)}
body.yagmur{background:linear-gradient(135deg,#373b44,#4286f4)}
body.kar{background:linear-gradient(135deg,#83a4d4,#b6fbff);color:#10283a}
body.gece{background:linear-gradient(135deg,#0f0c29,#302b63)}
.wrap{max-width:760px;margin:auto}
.cam{background:rgba(255,255,255,.14);backdrop-filter:blur(14px);border:1px solid rgba(255,255,255,.25);
 border-radius:20px;padding:20px;margin-bottom:16px}
.ara{display:flex;gap:8px;position:relative}
input{flex:1;padding:12px 16px;border-radius:12px;border:none;font-size:16px;outline:none}
button{padding:12px 16px;border:none;border-radius:12px;cursor:pointer;font-size:15px;background:#fff;color:#222}
#liste{position:absolute;top:50px;left:0;right:60px;background:#fff;color:#222;border-radius:12px;z-index:5;overflow:hidden}
#liste div{padding:10px 16px;cursor:pointer}#liste div:hover{background:#eee}
.ana{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}
.derece{font-size:72px;font-weight:700}.emoji{font-size:72px}
.detay{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px;text-align:center}
.detay b{display:block;font-size:18px}.detay span{opacity:.8;font-size:13px}
.oneri-baslik{font-size:26px;font-weight:800;margin-bottom:10px}
.kalin{border-left:6px solid #5ac8fa}.orta{border-left:6px solid #ffd60a}.ince{border-left:6px solid #ff9f0a}
ul{list-style:none}li{padding:4px 0}.ek li{background:rgba(0,0,0,.2);border-radius:10px;padding:8px 12px;margin-top:6px}
.gunler{display:grid;grid-template-columns:repeat(auto-fit,minmax(92px,1fr));gap:8px;text-align:center}
.gun{background:rgba(255,255,255,.12);border-radius:14px;padding:10px 4px;font-size:13px}
.gun .e{font-size:28px}.etiket{display:inline-block;margin-top:4px;padding:2px 8px;border-radius:8px;background:rgba(0,0,0,.25);font-size:12px}
@media(max-width:520px){.detay{grid-template-columns:repeat(2,1fr)}.derece,.emoji{font-size:56px}}
.wrap{position:relative;z-index:1}
.gun{cursor:pointer;border:2px solid transparent;transition:background .2s}
.gun.secili{border-color:#fff;background:rgba(255,255,255,.25)}
.saatlik{display:flex;gap:4px;overflow-x:auto;align-items:flex-end;padding-bottom:6px}
.sut{flex:0 0 38px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:150px;font-size:11px;padding:2px 0}
.cubuk{width:20px;border-radius:6px 6px 2px 2px;background:#5ac8fa}
.sut.yuksek .cubuk{background:#0a84ff}
.sut.gecti{opacity:.4}
.sut.simdi{background:rgba(255,255,255,.22);border-radius:10px}
.sut .mm{height:14px;opacity:.9}.sut .sa{font-weight:600;margin-top:3px}
#bg{position:fixed;inset:0;z-index:-2;background-size:cover;background-position:center;opacity:0;transition:opacity 1s,filter 1s}
#bg.gunes{filter:saturate(1.2) brightness(1.05)}
#bg.bulut{filter:grayscale(.3) brightness(.85)}
#bg.yagmur{filter:grayscale(.55) brightness(.65)}
#bg.kar{filter:brightness(.9) contrast(1.05)}
#bg.gece{filter:brightness(.4) saturate(.8)}
#golge{position:fixed;inset:0;z-index:-1;opacity:0;transition:opacity 1s;background:linear-gradient(rgba(0,0,0,.25),rgba(0,0,0,.5))}
body.resimli{color:#fff}body.resimli #golge{opacity:1}
#fx{position:fixed;inset:0;z-index:0;pointer-events:none}
#kredi{position:fixed;bottom:8px;right:12px;font-size:12px;z-index:3;text-shadow:0 1px 3px #000}
#kredi a{color:#fff}
</style></head><body>
<div id="bg"></div><div id="golge"></div><canvas id="fx"></canvas><div id="kredi"></div>
<div class="wrap">
<h1 style="font-size:20px;margin-bottom:12px">Hava Durumu ve Giyim Önerisi</h1>
<div class="cam ara">
 <input id="q" placeholder="Şehir ara... (ör. Naxçıvan, Bakı, İstanbul)" autocomplete="off">
 <button id="konum" title="Konumumu bul">📍</button><div id="liste" hidden></div>
</div>
<div id="icerik"><div class="cam">Yükleniyor...</div></div>
<footer style="font-size:13px;opacity:.85;line-height:1.6;margin:8px 4px 40px">
<p>Bu sayfada seçtiğin şehrin anlık hava durumunu, saatlik yağış tahminini ve 7 günlük tahmini görebilir, hissedilen sıcaklığa göre kalın mı ince mi giyineceğine dair öneri alabilirsin.</p>
<p>Hava verisi: <a href="https://open-meteo.com/" style="color:inherit">Open-Meteo.com</a> (CC BY 4.0).</p>
</footer>
</div>
<script>
const q = document.getElementById('q'), liste = document.getElementById('liste'), icerik = document.getElementById('icerik');
let zamanlayici;

q.addEventListener('input', () => {
  clearTimeout(zamanlayici);
  zamanlayici = setTimeout(async () => {
    if (q.value.trim().length < 2) { liste.hidden = true; return; }
    const sonuc = await (await fetch('/api/ara?q=' + encodeURIComponent(q.value))).json();
    liste.innerHTML = '';
    sonuc.forEach(s => {
      const d = document.createElement('div');
      d.textContent = s.name + (s.admin1 ? ', ' + s.admin1 : '') + ' (' + s.country + ')';
      d.onclick = () => { liste.hidden = true; q.value = s.name; yukle(s.latitude, s.longitude, s.name + (s.admin1 && s.admin1 !== s.name ? ', ' + s.admin1 : '')); };
      liste.appendChild(d);
    });
    liste.hidden = sonuc.length === 0;
  }, 300);
});

document.getElementById('konum').onclick = () => {
  if (!navigator.geolocation) return alert('Tarayıcın konumu desteklemiyor');
  navigator.geolocation.getCurrentPosition(
    async p => {
      const la = p.coords.latitude, lo = p.coords.longitude;
      let ad = 'Konumunuz';
      try {
        const k = await (await fetch('/api/konum?lat=' + la + '&lon=' + lo)).json();
        if (k.ad) ad = 'Konumunuz: ' + k.ad;
      } catch (e) {}
      yukle(la, lo, ad);
    },
    () => alert('Konum izni verilmedi'));
};

function temaSec(h) {
  const k = h.kod;
  if (h.gece) return 'gece';
  if ([71,73,75,77,85,86].includes(k)) return 'kar';
  if ([51,53,55,61,63,65,80,81,82,95,96,99].includes(k)) return 'yagmur';
  if (k <= 1) return 'gunes';
  return 'bulut';
}

// ---- Arka plan: konumun en bilinen yeri + hava durumuna göre efekt ----
let fxId, sonTema = '';

async function arkaPlan(lat, lon, tema) {
  sonTema = tema;
  fx(tema);
  const bg = document.getElementById('bg'), kredi = document.getElementById('kredi');
  bg.className = tema;
  try {
    const m = await (await fetch('/api/mekan?lat=' + lat + '&lon=' + lon)).json();
    if (m && m.resim) {
      const img = new Image();
      img.onload = () => {
        bg.style.backgroundImage = 'url("' + m.resim + '")';
        bg.style.opacity = 1;
        document.body.classList.add('resimli');
        kredi.innerHTML = '📸 ' + m.baslik + ' · <a href="' + m.link + '" target="_blank">Wikipedia</a>';
      };
      img.src = m.resim;
      return;
    }
  } catch (e) {}
  bg.style.opacity = 0;
  kredi.textContent = '';
}

function fx(tema) {
  const c = document.getElementById('fx'), g = c.getContext('2d');
  cancelAnimationFrame(fxId);
  c.width = innerWidth; c.height = innerHeight;
  g.clearRect(0, 0, c.width, c.height);
  if (tema !== 'yagmur' && tema !== 'kar') return;
  const kar = tema === 'kar';
  const damlalar = Array.from({length: kar ? 120 : 220}, () => ({
    x: Math.random() * c.width, y: Math.random() * c.height, s: Math.random() * 6,
    b: kar ? 1.5 + Math.random() * 3 : 12 + Math.random() * 14,   // boyut / uzunluk
    v: kar ? 0.6 + Math.random() * 1.4 : 9 + Math.random() * 7    // hız
  }));
  (function ciz() {
    g.clearRect(0, 0, c.width, c.height);
    g.strokeStyle = 'rgba(174,194,224,.6)'; g.fillStyle = 'rgba(255,255,255,.85)'; g.lineWidth = 1.2;
    for (const p of damlalar) {
      if (kar) { p.s += 0.02; p.x += Math.sin(p.s) * 0.6; g.beginPath(); g.arc(p.x, p.y, p.b, 0, 7); g.fill(); }
      else { g.beginPath(); g.moveTo(p.x, p.y); g.lineTo(p.x - 2, p.y + p.b); g.stroke(); }
      p.y += p.v;
      if (p.y > c.height) { p.y = -20; p.x = Math.random() * c.width; }
    }
    fxId = requestAnimationFrame(ciz);
  })();
}
window.addEventListener('resize', () => fx(sonTema));

function gunSec(i) {
  const h = window.sonHava, g = h.gunler[i], liste = h.saatlik[g.tarih] || [];
  document.querySelectorAll('.gun').forEach((e, k) => e.classList.toggle('secili', k === i));
  const tamAd = new Date(g.tarih + 'T12:00:00').toLocaleDateString('tr-TR', {weekday: 'long', day: 'numeric', month: 'long'});
  const on = i === 0 ? 'Bugün' : i === 1 ? 'Yarın' : '';
  document.getElementById('sh-baslik').textContent = '🌧️ Saatlik Yağış · ' + (on ? on + ' (' + tamAd + ')' : tamAd);

  const zirve = liste.reduce((a, b) => b.yagis > a.yagis ? b : a, {yagis: -1, saat: ''});
  const toplam = liste.reduce((t, x) => t + x.mm, 0);
  document.getElementById('sh-ozet').textContent = (zirve.yagis < 20 && toplam < 0.1)
    ? '☀️ Gün boyunca belirgin bir yağış beklenmiyor'
    : 'En yüksek ihtimal: ' + zirve.saat + ' (%' + zirve.yagis + ') · Toplam: ' + toplam.toFixed(1) + ' mm';

  document.getElementById('saatlik').innerHTML = liste.map(x => {
    const sa = x.saat.slice(0, 2);
    const cls = 'sut' + (x.yagis >= 60 ? ' yuksek' : '') + (i === 0 && sa === h.saat ? ' simdi' : '')
              + (i === 0 && sa < h.saat ? ' gecti' : '');
    return '<div class="' + cls + '" title="' + x.saat + ' · ' + x.sicaklik + '°C"><span>%' + x.yagis + '</span>'
         + '<div class="cubuk" style="height:' + Math.max(3, x.yagis * 0.85) + 'px"></div>'
         + '<span class="sa">' + sa + '</span><span class="mm">' + (x.mm > 0 ? x.mm.toFixed(1) : '') + '</span></div>';
  }).join('');
  // bugün seçiliyse şu anki saate kaydır
  const simdi = document.querySelector('.sut.simdi');
  if (simdi) simdi.scrollIntoView({inline: 'center', block: 'nearest'});
}

async function yukle(lat, lon, ad) {
  icerik.innerHTML = '<div class="cam">Yükleniyor...</div>';
  const h = await (await fetch('/api/hava?lat=' + lat + '&lon=' + lon)).json();
  if (h.hata) { icerik.innerHTML = '<div class="cam">⚠️ ' + h.hata + '</div>'; return; }
  const tema = temaSec(h);
  document.body.className = tema;
  arkaPlan(lat, lon, tema);
  const o = h.oneri;
  const gun = t => new Date(t + 'T12:00:00').toLocaleDateString('tr-TR', {weekday: 'short'});
  icerik.innerHTML = `
  <div class="cam">
    <div class="ana">
      <div><div style="font-size:20px">📍 ${ad}</div><div class="derece">${h.sicaklik}°</div>
        <div>${h.durum} · Hissedilen ${h.hissedilen}°</div></div>
      <div class="emoji">${h.emoji}</div>
    </div>
    <div class="detay">
      <div><b>${h.nem}%</b><span>Nem</span></div>
      <div><b>${h.ruzgar} km/s</b><span>Rüzgar</span></div>
      <div><b>%${h.yagis}</b><span>Yağış ihtimali</span></div>
      <div><b>${h.uv}</b><span>UV indeksi</span></div>
    </div>
  </div>
  <div class="cam ${o.tip}">
    <div class="oneri-baslik">${o.emoji} ${o.baslik}</div>
    <ul>${o.parcalar.map(p => '<li>✔️ ' + p + '</li>').join('')}</ul>
    <ul class="ek">${o.ekstra.map(e => '<li>' + e + '</li>').join('')}</ul>
  </div>
  <div class="cam"><div style="margin-bottom:10px;font-weight:600">7 Günlük Tahmin <span style="font-weight:400;opacity:.8;font-size:13px">(güne tıkla, saatlik yağışı gör)</span></div>
    <div class="gunler">${h.gunler.map((g, i) => `
      <div class="gun" onclick="gunSec(${i})"><div>${i === 0 ? 'Bugün' : gun(g.tarih)}</div><div class="e">${g.emoji}</div>
        <div>${g.max}° / ${g.min}°</div><div>☔ %${g.yagis}</div>
        <div class="etiket">${g.giyim}</div></div>`).join('')}
    </div></div>
  <div class="cam">
    <div id="sh-baslik" style="font-weight:600;margin-bottom:4px"></div>
    <div id="sh-ozet" style="margin-bottom:12px;opacity:.9"></div>
    <div class="saatlik" id="saatlik"></div>
  </div>`;
  window.sonHava = h;
  gunSec(0);
}

yukle(39.2089, 45.4122, 'Naxçıvan');  // başlangıç şehri
</script></body></html>"""

if __name__ == "__main__":
    yayinda = "PORT" in os.environ  # hosting servisleri PORT verir
    app.run(host="0.0.0.0" if yayinda else "127.0.0.1",
            port=int(os.environ.get("PORT", 5000)), debug=not yayinda)

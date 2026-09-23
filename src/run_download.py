import os
import re
import json
import sys
import time
import urllib.parse
from datetime import datetime

LINKS_FILE = "links.txt"
OUTPUT_DIR = "downloads"

def detect_platform(url):
    if "shopee" in url:
        return "shopee"
    if "shein" in url or "onelink.shein" in url:
        return "shein"
    return "unknown"

def clean_filename(name, max_len=80):
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", "-", name.strip())
    return name[:max_len] or f"produto_{int(time.time())}"

def extract_shopee_images(html):
    images = set()
    for m in re.finditer(r'(?:down-br\.img\.usercontent\.com|cf\.shopee\.com\.br/file|cf\.shopee\.com\.br)\\?/file\/([a-zA-Z0-9]+)', html):
        images.add(f"https://down-br.img.susercontent.com/file/{m.group(1)}")
    for m in re.finditer(r'file\x5c?/([a-zA-Z0-9]{20,40})', html):
        h = m.group(1)
        if len(h) >= 20:
            images.add(f"https://down-br.img.susercontent.com/file/{h}")
    return images

def extract_shein_images(page):
    images = set()
    for m in re.finditer(r'https?://img\.ltwebstatic\.com/(?:v4/j/pi|[^"\' ]+)', page):
        url = m.group(0).rstrip('",);')
        if "images" in url or "j/pi" in url:
            images.add(url)
    for m in re.finditer(r'//img\.ltwebstatic\.com/(?:v4/j/pi|[^"\' ]+)', page):
        url = "https:" + m.group(0).rstrip('",);')
        if "images" in url or "j/pi" in url:
            images.add(url)
    return images

def extract_videos(page):
    videos = set()
    for m in re.finditer(r'https?://[^"\' ]+?\.mp4[^"\' ]*', page):
        videos.add(m.group(0).rstrip('",);'))
    for m in re.finditer(r'"url"\s*:\s*"([^"]+\.mp4[^"]*)"', page):
        v = m.group(1).replace("\\/", "/")
        videos.add(v)
    return videos

def get_page_html(page, timeout_ms=25000):
    page.wait_for_load_state("networkidle", timeout=timeout_ms)
    time.sleep(3)
    return page.content()

def process_product(page, ctx, url, index):
    platform = detect_platform(url)
    print(f"\n[{index}] Plataforma: {platform}")
    print(f"[{index}] URL: {url}")

    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        if response is None:
            print(f"[{index}] Sem resposta HTTP")
            return
        print(f"[{index}] Status HTTP: {response.status}")
    except Exception as e:
        print(f"[{index}] Erro ao abrir: {e}")

    html = get_page_html(page)

    if platform == "shopee":
        images = extract_shopee_images(html)
        videos = extract_videos(html)
        # fallback: pega og:image
        mt = re.search(r'property="og:image"\s+content="([^"]+)"', html)
        if mt:
            images.add(mt.group(1))
    elif platform == "shein":
        # resolve página real se veio do onelink
        m = re.search(r'<input id="url" value="([^"]+)"', html)
        if m:
            real_url = m.group(1).replace("&amp;", "&")
            print(f"[{index}] URL real Shein: {real_url}")
            page.goto(real_url, wait_until="domcontentloaded", timeout=45000)
            html = get_page_html(page)
        images = extract_shein_images(html)
        videos = extract_videos(html)
        mt = re.search(r'property="og:image"\s+content="([^"]+)"', html)
        if mt:
            images.add(mt.group(1))
    else:
        print(f"[{index}] Plataforma não reconhecida")
        return

    print(f"[{index}] Imagens encontradas: {len(images)}")
    print(f"[{index}] Vídeos encontrados: {len(videos)}")

    if not images and not videos:
        print(f"[{index}] Nenhum media encontrado")
        return

    # título
    title = "produto"
    mt = re.search(r'property="og:title"\s+content="([^"]+)"', html)
    if mt:
        title = mt.group(1)
    elif '<title>' in html:
        mt = re.search(r'<title[^>]*>([^<]+)</title>', html)
        if mt:
            title = mt.group(1)

    safe = clean_filename(title)
    folder = os.path.join(OUTPUT_DIR, f"{platform}_{index}_{safe}")
    os.makedirs(folder, exist_ok=True)

    media_list = []
    for i, url_img in enumerate(sorted(images)):
        try:
            ext = ".jpg"
            if ".png" in url_img:
                ext = ".png"
            name = os.path.join(folder, f"imagem_{i+1}{ext}")
            resp = ctx.request.get(url_img, timeout=30000)
            if resp.ok:
                body = resp.body()
                if len(body) > 500:
                    with open(name, "wb") as f:
                        f.write(body)
                    print(f"[{index}] Imagem salva: {name} ({len(body)} bytes)")
                    media_list.append({"tipo": "imagem", "arquivo": name, "url": url_img, "bytes": len(body)})
                else:
                    print(f"[{index}] Imagem muito pequena, ignorada: {url_img}")
        except Exception as e:
            print(f"[{index}] Erro ao baixar imagem {url_img}: {e}")

    for i, v_url in enumerate(sorted(videos)):
        try:
            name = os.path.join(folder, f"video_{i+1}.mp4")
            resp = ctx.request.get(v_url, timeout=60000)
            if resp.ok:
                body = resp.body()
                if len(body) > 1000:
                    with open(name, "wb") as f:
                        f.write(body)
                    print(f"[{index}] Vídeo salvo: {name} ({len(body)} bytes)")
                    media_list.append({"tipo": "video", "arquivo": name, "url": v_url, "bytes": len(body)})
        except Exception as e:
            print(f"[{index}] Erro ao baixar vídeo {v_url}: {e}")

    info = {
        "plataforma": platform,
        "url_original": url,
        "titulo": title,
        "baixado_em": datetime.now().isoformat(),
        "medias": media_list,
    }
    with open(os.path.join(folder, "info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    print(f"[{index}] Concluído: {len(media_list)} mídias em {folder}")

def main():
    links = []
    if os.path.exists(LINKS_FILE):
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    links.append(line)

    # aceita link via argumento também: python run.py https://link
    if len(sys.argv) > 1:
        links = [a for a in sys.argv[1:] if a.startswith("http")]

    if not links:
        print("Nenhum link em links.txt. Adicione os links (um por linha).")
        print("Exemplo:")
        print("  https://s.shopee.com.br/xxxxx")
        print("  https://onelink.shein.com/xx/xxxx")
        sys.exit(1)

    print(f"Processando {len(links)} link(s)...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 2000},
            locale="pt-BR",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        for i, link in enumerate(links, 1):
            try:
                process_product(page, context, link, i)
            except Exception as e:
                print(f"[{i}] ERRO geral: {e}")
        browser.close()

    print("\n=== PROCESSAMENTO CONCLUÍDO ===")

if __name__ == "__main__":
    main()
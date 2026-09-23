import os
import re
import json
import sys
import time
from datetime import datetime

LINKS_FILE = "links.txt"
OUTPUT_DIR = "downloads"


def clean_filename(name, max_len=80):
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", "-", name.strip())
    return name[:max_len] or f"produto_{int(time.time())}"


def extract_shein_images(html):
    images = set()
    # imagens de produto (v4/j/pi)
    for m in re.finditer(r'https?://img\.ltwebstatic\.com/[^"\'\\>\s]+?\.(?:jpg|jpeg|png|webp)', html):
        url = m.group(0).rstrip('",);')
        if 'j/pi' in url or 'images' in url or 'good' in url:
            images.add(url)
    # og:image
    mt = re.search(r'property="og:image"\s+content="([^"]+)"', html)
    if mt:
        images.add(mt.group(1))
    return images


def extract_videos(html):
    videos = set()
    for m in re.finditer(r'https?://[^"\'\\>\s]+?\.mp4[^"\'\\>\s]*', html):
        v = m.group(0).rstrip('",);')
        videos.add(v)
    for m in re.finditer(r'"url"\s*:\s*"([^"]+\.mp4[^"]*)"', html):
        videos.add(m.group(1).replace("\\/", "/"))
    return videos


def process_product(page, ctx, url, index):
    print(f"\n[{index}] URL: {url}")

    # abre a página do produto (segue redirects)
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        print(f"[{index}] Status HTTP: {resp.status if resp else '?'}")
    except Exception as e:
        # erro de rede: tenta carregar mesmo assim (página pode ter carregado parcialmente)
        print(f"[{index}] Aviso ao abrir: {str(e)[:80]}")

    print(f"[{index}] Título: {page.title()[:60]}")

    # resolve onelink Shein → URL real do produto
    html = page.content()
    m = re.search(r'<input id="url" value="([^"]+)"', html)
    if m:
        real_url = m.group(1).replace("&amp;", "&")
        # limpa parâmetros de tracking, mantém só a URL do produto
        if "?" in real_url:
            base = real_url.split("?")[0]
            # tenta extrair product ID da URL
            pid_match = re.search(r'p-(\d+)', base)
            if pid_match:
                real_url = base
        print(f"[{index}] URL real: {real_url[:80]}")
        try:
            page.goto(real_url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print(f"[{index}] Aviso URL real: {str(e)[:80]}")
        page.wait_for_timeout(5000)
        html = page.content()

    # extrai imagens e vídeos
    images = extract_shein_images(html)
    videos = extract_videos(html)

    # scroll para forçar lazy-load
    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1000)
    html = page.content()
    images.update(extract_shein_images(html))
    videos.update(extract_videos(html))

    # tenta API de detalhes
    product_id = re.search(r'p-(\d+)', page.url)
    if product_id:
        pid = product_id.group(1)
        for ep in [
            f"https://br.shein.com/bff-api/goods-detail/v1/first-screen/{pid}",
            f"https://br.shein.com/aj/arc/goods/detail?goods_id={pid}&lang=pt&curr=brl",
        ]:
            try:
                r = page.evaluate(f"""async () => {{
                    try {{
                        const r = await fetch("{ep}", {{headers: {{'accept':'application/json'}}}});
                        return {{s: r.status, t: (await r.text()).slice(0,5000)}};
                    }} catch(e) {{ return {{e: String(e)}}; }}
                }}""")
                if r and r.get("s") == 200 and r.get("t"):
                    data = json.loads(r["t"])
                    goods = (data.get("data") or data.get("goods") or {})
                    if "goods_image" in goods:
                        for img in goods["goods_image"]:
                            if isinstance(img, str):
                                images.add(img if img.startswith("http") else "https:" + img)
                    if "goods_video" in goods:
                        for vid in goods["goods_video"]:
                            if isinstance(vid, str) and vid:
                                videos.add(vid if vid.startswith("http") else "https:" + vid)
                    break
            except Exception:
                pass

    print(f"[{index}] Imagens: {len(images)} | Vídeos: {len(videos)}")
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
    folder = os.path.join(OUTPUT_DIR, f"shein_{index}_{safe}")
    os.makedirs(folder, exist_ok=True)

    media_list = []
    for i, url_img in enumerate(sorted(images)):
        try:
            ext = ".png" if ".png" in url_img else ".jpg"
            name = os.path.join(folder, f"imagem_{i+1}{ext}")
            r = ctx.request.get(url_img, timeout=30000)
            if r.ok:
                body = r.body()
                if len(body) > 500:
                    with open(name, "wb") as f:
                        f.write(body)
                    print(f"[{index}]  imagem_{i+1}{ext} ({len(body)} bytes)")
                    media_list.append({"tipo": "imagem", "arquivo": name, "url": url_img, "bytes": len(body)})
        except Exception as e:
            print(f"[{index}] Erro imagem {i+1}: {e}")

    for i, v_url in enumerate(sorted(videos)):
        try:
            name = os.path.join(folder, f"video_{i+1}.mp4")
            r = ctx.request.get(v_url, timeout=60000)
            if r.ok:
                body = r.body()
                if len(body) > 1000:
                    with open(name, "wb") as f:
                        f.write(body)
                    print(f"[{index}]  video_{i+1}.mp4 ({len(body)} bytes)")
                    media_list.append({"tipo": "video", "arquivo": name, "url": v_url, "bytes": len(body)})
        except Exception as e:
            print(f"[{index}] Erro vídeo {i+1}: {e}")

    info = {
        "plataforma": "shein",
        "url_original": url,
        "titulo": title,
        "baixado_em": datetime.now().isoformat(),
        "total_imagens": len([m for m in media_list if m["tipo"] == "imagem"]),
        "total_videos": len([m for m in media_list if m["tipo"] == "video"]),
        "medias": media_list,
    }
    with open(os.path.join(folder, "info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print(f"[{index}] CONCLUÍDO: {len(media_list)} mídias em {folder}")


def main():
    links = []
    if os.path.exists(LINKS_FILE):
        with open(LINKS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    links.append(line)

    if len(sys.argv) > 1:
        links = [a for a in sys.argv[1:] if a.startswith("http")]

    if not links:
        print("Nenhum link encontrado em links.txt")
        print("Adicione links Shein (um por linha)")
        sys.exit(1)

    print(f"Processando {len(links)} link(s) Shein...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
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
                print(f"[{i}] ERRO: {e}")

        browser.close()

    print("\n=== PROCESSAMENTO CONCLUÍDO ===")


if __name__ == "__main__":
    main()
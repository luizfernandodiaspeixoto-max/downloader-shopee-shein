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
    # formato renderizado pelo navegador: https://down-br.img.susercontent.com/file/hash _gocd etc
    for m in re.finditer(r'(?:down-br\.img\.usercontent\.com|sg\.img\.usercontent\.com)/(?:file|files?)/([a-zA-Z0-9]{10,})', html):
        images.add(f"https://down-br.img.susercontent.com/file/{m.group(1)}")
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

def collect_all_images(page):
    """Extrai todas URLs de imagem do DOM renderizado (mais confiável que regex no HTML)."""
    urls = page.evaluate("""() => {
        const out = new Set();
        document.querySelectorAll('img').forEach(img => {
            ['src', 'data-src', 'data-original', 'data-lazy'].forEach(attr => {
                const v = img.getAttribute(attr);
                if (v) out.add(v);
            });
        });
        document.querySelectorAll('[style*="url("]').forEach(el => {
            const m = el.style.cssText.match(/url\(["']?([^"')]+)["']?\)/g) || [];
            m.forEach(x => out.add(x.replace(/url\(["']?|["']?\)/g, '')));
        });
        document.querySelectorAll('source').forEach(s => {
            const v = s.getAttribute('srcset') || s.getAttribute('src');
            if (v) out.add(v.split(' ')[0]);
        });
        return Array.from(out);
    }""")
    return [u for u in urls if u.startswith("http") and ".svg" not in u.lower()]

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

    print(f"[{index}] Título da página: {page.title()[:60]}")
    print(f"[{index}] URL atual: {page.url[:120]}")

    # se for link encurtado da Shopee e ainda não redirecionou, aguarda redirecionamento JS
    if "s.shopee.com.br" in url and "opaanlp" not in page.url and "shopee.com.br" not in page.url.replace("s.shopee.com.br", ""):
        try:
            page.wait_for_url(lambda u: "shopee.com.br" in u and "s.shopee" not in u, timeout=30000)
            print(f"[{index}] Redirecionado: {page.url[:120]}")
        except Exception:
            print(f"[{index}] Aviso: não redirecionou para página interna")
    html = get_page_html(page)

    if platform == "shopee":
        # Estratégia: visitar homepage (sem anti-bot) para obter cookies,
        # depois chamar a API via fetch interno (herda cookies + headers legítimos)
        api_images = set()
        api_video = None
        api_name = None
        link_ids = None
        try:
            # extrai IDs do link encurtado (antes de redirecionar para verify/error)
            link_ids = re.search(r'shopee\.com\.br/([a-z0-9]+)/(\d+)/(\d+)', url)
            if not link_ids:
                link_ids = re.search(r'/(\d+)/(\d+)(?:\?|$)', page.url)
            m = link_ids
            print(f"[{index}] IDs extraídos: matched={bool(m)} url_base={url[:80]}")
            if m:
                groups = m.groups()
                if len(groups) >= 3:
                    shop_id, item_id = groups[1], groups[2]
                else:
                    shop_id, item_id = groups[0], groups[1]
                print(f"[{index}] shop_id={shop_id} item_id={item_id}")

                # passo 1: visita homepage para obter cookies legítimos
                page.goto("https://shopee.com.br", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)
                print(f"[{index}] Homepage Shopee carregada, cookies obtidos")

                # passo 2: tenta múltiplos endpoints da API via fetch interno
                api_urls = [
                    f"https://shopee.com.br/api/v4/item/get?shopid={shop_id}&itemid={item_id}",
                    f"https://shopee.com.br/api/v4/pdp/get_pc?item_id={item_id}&shop_id={shop_id}",
                ]
                for api_url in api_urls:
                    result = page.evaluate(f"""async () => {{
                        try {{
                            const r = await fetch("{api_url}", {{
                                headers: {{
                                    'x-api-source': 'pc',
                                    'x-requested-with': 'XMLHttpRequest',
                                    'x-shopee-language': 'pt',
                                    'accept': 'application/json'
                                }}
                            }});
                            const txt = await r.text();
                            return {{status: r.status, body: txt.slice(0, 5000)}};
                        }} catch(e) {{ return {{error: String(e)}}; }}
                    }}""")
                    status = (result or {}).get("status")
                    body = (result or {}).get("body", "")
                    print(f"[{index}] API {api_url.split('?')[0].split('/')[-1]}: status={status} len={len(body)}")
                    if status == 200 and body:
                        try:
                            import json as _json
                            data = _json.loads(body)
                            item_data = data.get("data") or {}
                            if "item" in item_data:
                                item_data = item_data["item"]
                            name = item_data.get("name")
                            imgs = item_data.get("images")
                            vid = item_data.get("video")
                            if imgs:
                                for h in imgs:
                                    api_images.add(f"https://down-br.img.susercontent.com/file/{h}")
                                api_video = vid
                                api_name = name
                                print(f"[{index}] API OK: {len(imgs)} imagens, video={'sim' if vid else 'nao'}")
                                break
                        except Exception as e:
                            print(f"[{index}] Erro parse: {e}")
                    elif status == 403:
                        print(f"[{index}] API bloqueada (403)")
        except Exception as e:
            print(f"[{index}] API via fetch falhou: {e}")

        # fallback: tenta extrair do HTML da página do produto via fetch HTML
        if not api_images:
            try:
                sid = m.group(1) if m and len(m.groups()) >= 1 else None
                iid = m.group(2) if m and len(m.groups()) >= 2 else None
                if not sid or not iid:
                    link_ids2 = re.search(r'shopee\.com\.br/([a-z0-9]+)/(\d+)/(\d+)', url)
                    if link_ids2:
                        g = link_ids2.groups()
                        sid, iid = g[1], g[2]
                if sid and iid:
                    product_url = f"https://shopee.com.br/opaanlp/{sid}/{iid}"
                    html_result = page.evaluate(f"""async () => {{
                        try {{
                            const r = await fetch("{product_url}", {{
                                headers: {{'accept': 'text/html'}},
                                redirect: 'follow'
                            }});
                            const html = await r.text();
                            return html.slice(0, 50000);
                        }} catch(e) {{ return ''; }}
                    }}""")
                    if html_result:
                        print(f"[{index}] HTML fetch: {len(html_result)} chars")
                        html = html_result
                        for u in re.findall(r'https?://[^"\'\\s<>]+down-br\.img\.usercontent\.com/file/[a-zA-Z0-9]+', html):
                            api_images.add(u.split('"')[0].split("'")[0])
                        for u in re.findall(r'https?://[^"\'\\s<>]+\.mp4[^"\'\\s<>]*', html):
                            api_video = u.split('"')[0]
                        if '<title>' in html_result:
                            t = re.search(r'<title>([^<]+)', html_result)
                            if t:
                                api_name = t.group(1)
            except Exception as e:
                print(f"[{index}] HTML fallback falhou: {e}")

        # continua com scroll/extração DOM
        for _ in range(4):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2500)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(2000)
        html = page.content()
        images = extract_shopee_images(html)
        all_urls = collect_all_images(page)
        for u in all_urls:
            if "img.susercontent.com" in u or "shopee.com.br/file" in u or "file/" in u:
                clean = u.split(".image")[0].split("_webp")[0]
                if ".jpg" in clean or ".png" in clean or "/file/" in clean or "sfile" in clean:
                    images.add(clean.replace("_gocd", "").replace(" ", ""))
        images.update(api_images)
        videos = extract_videos(html)
        if api_video:
            videos.add(f"https://down-br.img.susercontent.com/file/{api_video}")
        mt = re.search(r'property="og:image"\s+content="([^"]+)"', html)
        if mt:
            images.add(mt.group(1))
        if api_name:
            mt2 = re.search(r'property="og:title"\s+content="([^"]+)"', html)
            if not mt2:
                html = html.replace("<head>", f'<head><meta property="og:title" content="{api_name}">')
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
            extra_http_headers={
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        # stealth: esconde sinais de automação
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            window.chrome = {runtime: {}};
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({state: Notification.permission}) :
                originalQuery(parameters)
            );
        """)
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
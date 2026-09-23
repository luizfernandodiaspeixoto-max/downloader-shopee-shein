import os
import re
import json
import time
import asyncio
from datetime import datetime
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "COLE_SEU_TOKEN_AQUI")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot de Download Shein\n\n"
        "Envie um link de produto Shein e eu baixo todas as fotos e videos.\n\n"
        "Exemplo:\nhttps://onelink.shein.com/53/xxxxx\nhttps://br.shein.com/produto-p-123.html"
    )

async def download_shein(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if "shein" not in url.lower():
        await update.message.reply_text("Envie apenas links da Shein.")
        return

    status = await update.message.reply_text("Processando link Shein...")
    
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            context_pw = await browser.new_context(
                viewport={"width": 1280, "height": 2000},
                locale="pt-BR",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context_pw.new_page()
            
            await status.edit_text("Abrindo link...")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                pass
            
            html = await page.content()
            
            # resolve onelink
            m = re.search(r'<input id="url" value="([^"]+)"', html)
            if m:
                real_url = m.group(1).replace("&amp;", "&").split("?")[0]
                await status.edit_text("Carregando produto...")
                try:
                    await page.goto(real_url, wait_until="domcontentloaded", timeout=45000)
                except Exception:
                    pass
                await asyncio.sleep(5)
                html = await page.content()
            
            # extrai titulo
            title = "produto"
            mt = re.search(r'property="og:title"\s+content="([^"]+)"', html)
            if mt:
                title = mt.group(1)
            elif '<title>' in html:
                mt = re.search(r'<title[^>]*>([^<]+)</title>', html)
                if mt:
                    title = mt.group(1)
            
            await status.edit_text(f"Extraindo imagens de:\n{title[:50]}...")
            
            # scroll para lazy-load
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            html = await page.content()
            
            # extrai imagens
            images = set()
            for m in re.finditer(r'https?://img\.ltwebstatic\.com/[^"\'\\>\s]+?\.(?:jpg|jpeg|png|webp)', html):
                url_img = m.group(0).rstrip('",);')
                if 'j/pi' in url_img or 'images' in url_img or 'good' in url_img:
                    images.add(url_img)
            mt = re.search(r'property="og:image"\s+content="([^"]+)"', html)
            if mt:
                images.add(mt.group(1))
            
            # extrai videos
            videos = set()
            for m in re.finditer(r'https?://[^"\'\\>\s]+?\.mp4[^"\'\\>\s]*', html):
                videos.add(m.group(0).rstrip('",);'))
            
            await browser.close()
            
            if not images and not videos:
                await status.edit_text("Nenhum media encontrado no link.")
                return
            
            await status.edit_text(f"Encontrado {len(images)} imagens e {len(videos)} videos. Baixando...")
            
            # cria pasta temporaria
            os.makedirs("temp", exist_ok=True)
            product_folder = f"temp/{title[:30].replace(' ', '_')}"
            os.makedirs(product_folder, exist_ok=True)
            
            sent_count = 0
            
            # envia imagens
            for i, img_url in enumerate(sorted(images)[:10], 1):  # limita a 10
                try:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(img_url, timeout=30)
                        if resp.status_code == 200 and len(resp.content) > 500:
                            ext = "png" if ".png" in img_url else "jpg"
                            filename = f"{product_folder}/imagem_{i}.{ext}"
                            with open(filename, "wb") as f:
                                f.write(resp.content)
                            with open(filename, "rb") as f:
                                await update.message.reply_photo(
                                    photo=f,
                                    caption=f"Imagem {i}/{min(len(images), 10)} - {title[:40]}"
                                )
                            sent_count += 1
                            await asyncio.sleep(0.5)
                except Exception as e:
                    pass
            
            # envia videos
            for i, vid_url in enumerate(sorted(videos)[:3], 1):  # limita a 3
                try:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(vid_url, timeout=60)
                        if resp.status_code == 200 and len(resp.content) > 1000:
                            filename = f"{product_folder}/video_{i}.mp4"
                            with open(filename, "wb") as f:
                                f.write(resp.content)
                            with open(filename, "rb") as f:
                                await update.message.reply_video(
                                    video=f,
                                    caption=f"Video {i} - {title[:40]}"
                                )
                            sent_count += 1
                            await asyncio.sleep(1)
                except Exception as e:
                    pass
            
            # limpa arquivos temporarios
            import shutil
            shutil.rmtree(product_folder, ignore_errors=True)
            
            await status.edit_text(
                f"Concluido!\n\n"
                f"Produto: {title[:60]}\n"
                f"Enviado: {sent_count} arquivos\n"
                f"Imagens: {min(len(images), 10)} | Videos: {min(len(videos), 3)}"
            )
    
    except Exception as e:
        await status.edit_text(f"Erro: {str(e)[:200]}")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_shein))
    
    print("Bot Shein iniciado!")
    app.run_polling()

if __name__ == "__main__":
    main()
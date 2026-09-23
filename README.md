# 📦 Downloader Automático - Shein

Baixa imagens e vídeos de produtos da **Shein** automaticamente usando **GitHub Actions** (grátis).

## Como funciona

1. Você cola links de produtos Shein em `links.txt`
2. O GitHub Actions roda automaticamente (2x/dia) ou manualmente
3. O script usa Chromium headless para extrair fotos e vídeos
4. Os arquivos ficam em **Actions → Artifacts** para download

## Setup (5 min)

1. Crie um repositório público no GitHub: [github.com/new](https://github.com/new)
2. Envie estes arquivos:
```bash
cd G:\video-shopee-shein
git init
git add .
git commit -m "Shein downloader"
git remote add origin https://github.com/SEU_USER/SEU_REPO.git
git push -u origin main
```
3. Em `links.txt`, cole os links dos produtos
4. Faça push → o workflow roda sozinho

## Baixando resultados

- Vá em **Actions → run mais recente → Artifacts**
- Clique em **shein-downloads** para baixar .zip

## Estrutura

```
├── links.txt              ← Cole os links aqui (1 por linha)
├── src/run_download.py    ← Script principal
├── .github/workflows/
│   └── download.yml       ← Automação (2x/dia)
├── downloads/             ← Imagens e vídeos baixados
└── README.md
```

## Exemplo de `links.txt`

```
https://onelink.shein.com/53/62qcn1cb2xcn?ismg_ol=XXXX
```

## Resultado para cada produto

Uma pasta com:
- `imagem_1.jpg`, `imagem_2.jpg`, ... (fotos do produto)
- `video_1.mp4` (se disponível)
- `info.json` (título, URL, metadados)
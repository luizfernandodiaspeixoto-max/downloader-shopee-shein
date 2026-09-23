# � 📦 Downloader Automático - Shopee/Shein

Baixa imagens e vídeos de produtos da Shopee/Shein automaticamente usando **GitHub Actions** (grátis).

## 🚀 Como funciona

1. Você cola os links dos produtos em `links.txt` (um por linha)
2. O GitHub Actions roda o script (`src/run_download.py`) que:
   - Abre cada link num navegador headless (Chromium)
   - Extrai imagens e vídeos do produto
   - Salva em `downloads/<produto>/`
3. Você baixa os arquivos em **Actions → run mais recente → Artifacts**

## ⏰ Agendamento automático

O workflow roda sozinho **2x por dia** (08:00 e 20:00 UTC), além de rodar:
- Manualmente (botão "Run workflow")
- Automaticamente quando você alterar `links.txt` ou `src/`

## 📋 Configuração inicial (5 min)

1. Crie um repositório no GitHub: [github.com/new](https://github.com/new) (público = grátis)
2. Envie estes arquivos para o repositório:
```bash
git init
git add .
git commit -m "Downloader Shopee/Shein"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/SEU_REPO.git
git push -u origin main
```
3. Em `links.txt`, adicione os links dos produtos
4. Commite e faça push. O workflow roda sozinho!

## 📥 Baixando os resultados

- Vá em **Actions → run mais recente → Artifacts → downloads**
- Ou clone o repositório: `git pull` (resultados também são commitados de volta)

## 🗂 Estrutura

```
├── links.txt              # Entrada: links dos produtos (1 por linha)
├── src/run_download.py    # Script principal (Playwright)
├── .github/workflows/
│   └── download.yml       # Automação GitHub Actions
├── downloads/             # Saída: fotos e vídeos baixados
└── README.md
```

## ✅ Exemplo de `links.txt`

```
# Shopee
https://s.shopee.com.br/112xJKPa8F
# Shein
https://onelink.shein.com/53/62qcn1cb2xcn?ismg_ol=XXXX
```

## 🎯 Resultado esperado

Para cada produto, uma pasta com:
- `imagem_1.jpg`, `imagem_2.jpg`, ... (fotos do produto)
- `video_1.mp4` (vídeo, se disponível)
- `info.json` (título, data, metadados)

## ⚠️ Observações

- Limite grátis GitHub Actions: 2000 min/mês (repo público)
- Sites podem bloquear acessos em massa; use com moderação
- Se um produto não tiver vídeo, apenas as imagens serão baixadas
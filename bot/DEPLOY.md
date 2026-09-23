# Bot Telegram Shein - Deploy

## 1. Criar bot no Telegram
1. Abra o Telegram e busque **@BotFather**
2. Envie `/newbot`
3. Escolha um nome: `Shein Download Bot`
4. Escolha um username: `seu_shein_bot`
5. Copie o **TOKEN** (algo como `123456:ABC-DEF...`)

## 2. Deploy no Render.com (grátis)
1. Crie conta em [render.com](https://render.com)
2. Clique **New** → **Background Worker**
3. Conecte seu repositório GitHub
4. Configure:
   - **Name:** shein-bot
   - **Runtime:** Python
   - **Build Command:** `pip install -r bot/requirements.txt && python -m playwright install chromium --with-deps`
   - **Start Command:** `python bot/telegram_bot.py`
5. Em **Environment Variables**, adicione:
   - **Key:** `TELEGRAM_TOKEN`
   - **Value:** `SEU_TOKEN_AQUI`
6. Clique **Create Web Service**

## 3. Usar o bot
1. Abra o Telegram
2. Busque seu bot pelo username
3. Envie `/start`
4. Cole um link Shein
5. Aguarde as fotos e vídeos!

## Limites grátis Render
- 750 horas/mês
- Dorme após 15 min sem requests (mas acorda quando você manda mensagem)
- Ideal para uso pessoal
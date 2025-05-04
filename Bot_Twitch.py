import os
import requests
import time
from datetime import datetime, timedelta
from twitchio.ext import commands
import google.generativeai as genai
from dotenv import load_dotenv
import wow_comparative  # Importa o módulo com as funções de comparação
import pandas as pd  # Importação necessária para manipular DataFrames
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ========== CARREGAMENTO DE VARIÁVEIS DE AMBIENTE ==========
load_dotenv()

# ========== CONFIGURAÇÕES DO YOUTUBE ==========
YOUTUBE_VIDEO_ID = os.getenv("YOUTUBE_VIDEO_ID")
TOKEN_FILE = os.getenv("TOKEN_FILE", "token.json")
CLIENT_SECRETS_FILE = os.getenv("CLIENT_SECRETS_FILE")
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

# ========== CONFIGURAÇÃO DO GEMINI ==========
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    generation_config=generation_config,
)

# ========== CONFIGURAÇÕES DA TWITCH ==========
CANAL = os.getenv("TWITCH_CANAL")
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
REFRESH_TOKEN = os.getenv("TWITCH_REFRESH_TOKEN")
REFRESH_API_URL = f"https://twitchtokengenerator.com/api/refresh/{REFRESH_TOKEN}"

# ========== GOOGLE SHEETS ==========
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "174Hx2g3gZ1IV6OztcmeLUfGi8ahH3sYwG2803kcNVew")
SHEET_NAME = os.getenv("SHEET_NAME", "Player_status")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE")

# ========== FUNÇÕES AUXILIARES YOUTUBE ==========
def get_youtube_service():
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes=SCOPES)
    return build("youtube", "v3", credentials=creds)

def get_chat_id_from_video(youtube, video_id):
    request = youtube.videos().list(part="liveStreamingDetails", id=video_id)
    response = request.execute()
    items = response.get("items", [])
    if items and "liveStreamingDetails" in items[0]:
        return items[0]["liveStreamingDetails"].get("activeLiveChatId")
    return None

def enviar_resposta_youtube(texto):
    youtube = get_youtube_service()
    chat_id = get_chat_id_from_video(youtube, YOUTUBE_VIDEO_ID)
    if chat_id:
        youtube.liveChatMessages().insert(
            part="snippet",
            body={
                "snippet": {
                    "liveChatId": chat_id,
                    "type": "textMessageEvent",
                    "textMessageDetails": {
                        "messageText": texto
                    }
                }
            }
        ).execute()

# ========== OBTENDO TOKEN TWITCH ==========
def obter_token_via_refresh():
    try:
        print("🔄 Obtendo novo token via refresh...")
        response = requests.get(REFRESH_API_URL)
        data = response.json()

        if response.status_code == 200 and "token" in data and "refresh" in data:
            print("✅ Novo token obtido com sucesso!")
            return {
                "access_token": data["token"],
                "refresh_token": data["refresh"]
            }
        else:
            print(f"❌ Erro ao obter novo token: {data}")
            return None
    except Exception as e:
        print(f"⚠️ Exceção ao obter token: {e}")
        return None

token_data = obter_token_via_refresh()
if token_data:
    TOKEN = token_data["access_token"]
    REFRESH_TOKEN = token_data["refresh_token"]
    print(f"🔑 Token de acesso: {TOKEN[:5]}...")
else:
    print("🚨 Falha ao obter token.")
    TOKEN = None

# ========== CLASSE DO BOT ==========
class MeuBot(commands.Bot):
    def __init__(self):
        if not TOKEN:
            raise ValueError("🚨 Token não disponível. Não é possível inicializar o bot.")

        super().__init__(
            token=TOKEN,
            client_id=CLIENT_ID,
            prefix="!",
            initial_channels=[CANAL],
            nick=CANAL
        )

        self.cooldown_usuarios = {}

    async def event_ready(self):
        print(f"✅ Bot {self.nick} conectado ao canal {CANAL}!")

    async def event_message(self, message):
        if message.echo:
            return
        print(f"💬 Mensagem recebida de {message.author.name}: {message.content}")
        await self.handle_commands(message)

    @commands.command(name="compare")
    async def compare_character(self, ctx):
        parts = ctx.message.content.split()
        if len(parts) < 3:
            await ctx.send("Uso correto: !compare <realm_slug> <character_slug>")
            return

        realm_slug = parts[1].lower()
        character_slug = parts[2].lower()

        try:
            token = wow_comparative.get_access_token(os.getenv("BLIZZARD_CLIENT_ID"), os.getenv("BLIZZARD_CLIENT_SECRET"))
            character_data = wow_comparative.get_character_data("us", realm_slug, character_slug, token)
            character_stats = wow_comparative.get_character_statistics("us", realm_slug, character_slug, token)

            if character_data is None:
                await ctx.send(f"Erro ao buscar dados do personagem '{character_slug}' no servidor '{realm_slug}'.")
                return

            character_data.update(character_stats)

            for key, value in character_data.items():
                if value is None or (isinstance(value, float) and (pd.isna(value) or value in [float('inf'), float('-inf')])):
                    character_data[key] = 0

            new_data = pd.DataFrame([character_data])
            wow_comparative.update_google_sheets(new_data, SPREADSHEET_ID, SHEET_NAME, CREDENTIALS_FILE)

            df = wow_comparative.get_google_sheets_df(SPREADSHEET_ID, SHEET_NAME, CREDENTIALS_FILE)
            percentile = wow_comparative.calculate_percentile(df, character_slug, realm_slug)

            if percentile is None:
                await ctx.send(f"✅ Dados de '{character_slug}' foram buscados na API e salvos na planilha! (Não foi possível calcular o percentil)")
            else:
                await ctx.send(f"✅ Dados de '{character_slug}' salvos! 🎯 Percentil: {percentile:.2f}% em Achievement Points.")

        except Exception as e:
            print(f"❌ Erro ao processar a comparação: {e}")
            await ctx.send(f"Erro ao processar a comparação: {e}")

    @commands.command(name="pergunta")
    async def pergunta_gemini(self, ctx):
        autor = ctx.author.name
        prompt = ctx.message.content.replace("!pergunta", "").strip()
        agora = datetime.utcnow()
        tempo_limite = timedelta(seconds=60)

        if autor in self.cooldown_usuarios:
            tempo_restante = (self.cooldown_usuarios[autor] + tempo_limite) - agora
            if tempo_restante.total_seconds() > 0:
                segundos = int(tempo_restante.total_seconds())
                await ctx.send(f"⏳ {autor}, espere {segundos}s antes de usar esse comando novamente.")
                return

        if not prompt:
            await ctx.send(f"{autor}, envie uma pergunta após o comando. Ex: !pergunta Qual o maior planeta?")
            return

        try:
            await ctx.send("🤖 Pensando...")
            response = model.generate_content(prompt)
            resposta = response.text.strip()

            if not resposta:
                resposta = "Desculpe, não consegui pensar em nada agora. 😅"

            resposta = "[IA] " + resposta
            if len(resposta) > 490:
                resposta = resposta[:490] + "..."

            await ctx.send(resposta)
            enviar_resposta_youtube(f"[Pergunta Twitch] {prompt}\n{resposta}")
            self.cooldown_usuarios[autor] = agora

        except Exception as e:
            print(f"❌ Erro ao gerar resposta com Gemini: {e}")
            await ctx.send("⚠️ Ocorreu um erro ao consultar a IA. Tente novamente.")

# ========== INICIALIZAÇÃO ==========
if __name__ == "__main__":
    if not TOKEN:
        print("🚨 Token não obtido. Não é possível iniciar o bot.")
        exit(1)

    try:
        print("🎬 Iniciando o bot da Twitch...")
        print(f"📡 Canal: {CANAL}")
        print(f"🆔 Client ID: {CLIENT_ID}")

        bot = MeuBot()
        bot.run()
    except Exception as e:
        print(f"❌ Erro ao iniciar o bot: {e}")
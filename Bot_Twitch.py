import os
import requests
import time
from datetime import datetime, timedelta
from twitchio.ext import commands
import google.generativeai as genai
from dotenv import load_dotenv
import wow_comparative  # Importa o módulo com as funções de comparação
import pandas as pd  # Importação necessária para manipular DataFrames

# ========== CARREGAMENTO DE VARIÁVEIS DE AMBIENTE ==========
load_dotenv()

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

    def obter_broadcaster_id(self):
        """Obtém o ID do streamer (broadcaster) para uso na API da Twitch."""
        url = "https://api.twitch.tv/helix/users"
        headers = {
            "Client-ID": CLIENT_ID,
            "Authorization": f"Bearer {TOKEN}"
        }
        try:
            response = requests.get(url, headers=headers)
            data = response.json()
            return data["data"][0]["id"] if "data" in data and data["data"] else None
        except Exception as e:
            print(f"❌ Erro ao obter broadcaster_id: {e}")
            return None

    def enviar_enquete(self, titulo, opcoes):
        """
        Cria uma enquete na Twitch via API.
        
        Args:
            titulo: Título da enquete
            opcoes: Lista de opções para a enquete
        
        Returns:
            bool: True se a enquete foi criada com sucesso
        """
        broadcaster_id = self.obter_broadcaster_id()
        if not broadcaster_id:
            print("❌ Não foi possível obter o broadcaster_id")
            return False
            
        try:
            url = "https://api.twitch.tv/helix/polls"
            headers = {
                "Client-ID": CLIENT_ID,
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json"
            }
            
            # Garantir que o título e opções estejam dentro dos limites da Twitch
            titulo = titulo[:60]  # Máximo de 60 caracteres
            opcoes_formatadas = [{"title": op[:25]} for op in opcoes[:5]]  # Máx 5 opções de 25 caracteres
            
            body = {
                "broadcaster_id": broadcaster_id,
                "title": titulo,
                "choices": opcoes_formatadas,
                "duration": 180  # Duração de 3 minutos (180 segundos)
            }

            response = requests.post(url, headers=headers, json=body)
            print(f"🔁 Resposta API Twitch: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Erro ao criar enquete: {e}")
            return False

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

    @commands.command(name="enquete")
    async def cmd_enquete(self, ctx):
        """
        Comando que permite ao dono do canal criar uma enquete gerada por IA.
        Uso: !enquete tema da enquete
        """
        autor = ctx.author.name.lower()
        canal = CANAL.lower()
        
        # Verificar se quem enviou o comando é o dono do canal
        if autor != canal:
            await ctx.send(f"⛔ Apenas o dono do canal pode criar enquetes!")
            return
        
        # Extrair o tema da enquete do comando
        prompt_usuario = ctx.message.content.replace("!enquete", "").strip()
        
        # Se não houver tema, usar um prompt genérico
        if not prompt_usuario:
            prompt = "Crie uma enquete criativa e divertida com 3 opções para uma live de games."
        else:
            prompt = f"Crie uma enquete divertida com 3 opções sobre: {prompt_usuario}"
        
        try:
            await ctx.send("🧠 Gerando enquete, aguarde...")
            
            # Consultar a IA para criar uma enquete
            response = model.generate_content(prompt)
            resposta = response.text.strip()
            
            # Processar a resposta para extrair título e opções
            linhas = resposta.splitlines()
            titulo = linhas[0].strip()
            
            # Extrair opções (linhas que começam com traço, asterisco ou número)
            opcoes = []
            for linha in linhas[1:]:
                linha_limpa = linha.strip()
                if linha_limpa and (linha_limpa.startswith('-') or 
                                   linha_limpa.startswith('*') or 
                                   linha_limpa.startswith('•') or
                                   (linha_limpa[0].isdigit() and linha_limpa[1:2] in [')', '.', ':'])):
                    opcao = linha_limpa.lstrip('-*•0123456789). :').strip()
                    opcoes.append(opcao)
            
            # Se não conseguimos extrair pelo menos 2 opções, não podemos criar a enquete
            if len(opcoes) < 2:
                await ctx.send("❌ Não consegui gerar opções suficientes para a enquete.")
                return
            
            # Limitar a 5 opções (máximo permitido pela Twitch)
            opcoes = opcoes[:5]
            
            # Criar a enquete
            sucesso = self.enviar_enquete(titulo, opcoes)
            
            if sucesso:
                await ctx.send(f"📊 Enquete criada: {titulo}")
            else:
                await ctx.send("❌ Falha ao criar a enquete. Verifique se o token tem permissão para gerenciar enquetes (channel:manage:polls).")
        
        except Exception as e:
            print(f"❌ Erro ao processar comando enquete: {e}")
            await ctx.send("⚠️ Ocorreu um erro ao gerar ou enviar a enquete.")

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

            resposta_formatada = "[IA] " + resposta
            if len(resposta_formatada) > 490:
                resposta_formatada = resposta_formatada[:490] + "..."

            await ctx.send(resposta_formatada)
            self.cooldown_usuarios[autor] = agora
            
        except Exception as e:
            print(f"❌ Erro ao gerar resposta com Gemini: {e}")
            await ctx.send("⚠️ Ocorreu um erro ao consultar a IA. Tente novamente.")

# Exemplo de uso para testes locais
if __name__ == "__main__":
    try:
        print("🎬 Iniciando o bot da Twitch...")
        print(f"📡 Canal: {CANAL}")
        print(f"🆔 Client ID: {CLIENT_ID}")

        bot = MeuBot()
        bot.run()
    except Exception as e:
        print(f"❌ Erro ao iniciar o bot: {e}")

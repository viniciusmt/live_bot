import os
import requests
import time
from datetime import datetime, timedelta
from twitchio.ext import commands
import google.generativeai as genai
from dotenv import load_dotenv
import wow_comparative  # Importa o módulo com as funções de comparação
import pandas as pd  # Importação necessária para manipular DataFrames
import traceback  # Para logs de erro mais detalhados

# ========== CARREGAMENTO DE VARIÁVEIS DE AMBIENTE ==========
load_dotenv()

# ========== CONFIGURAÇÃO DO GEMINI ==========
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("❌ GEMINI_API_KEY não está definida. O bot não funcionará corretamente.")
else:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        generation_config = {
            "temperature": 0.9,  # Ajustei para um valor mais comum
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 1024,  # Reduzido para respostas mais concisas
            "response_mime_type": "text/plain",
        }
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            generation_config=generation_config,
        )
        print("✅ Modelo Gemini configurado com sucesso")
    except Exception as e:
        print(f"❌ Erro ao configurar o Gemini: {e}")
        model = None

# ========== CONFIGURAÇÕES DA TWITCH ==========
CANAL = os.getenv("TWITCH_CANAL")
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
REFRESH_TOKEN = os.getenv("TWITCH_REFRESH_TOKEN")
REFRESH_API_URL = f"https://twitchtokengenerator.com/api/refresh/{REFRESH_TOKEN}"

# Verificar se as variáveis essenciais estão definidas
if not CANAL:
    print("❌ TWITCH_CANAL não está definido. O bot não funcionará corretamente.")
if not CLIENT_ID:
    print("❌ TWITCH_CLIENT_ID não está definido. O bot não funcionará corretamente.")
if not REFRESH_TOKEN:
    print("❌ TWITCH_REFRESH_TOKEN não está definido. O bot não funcionará corretamente.")

# ========== GOOGLE SHEETS ==========
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "174Hx2g3gZ1IV6OztcmeLUfGi8ahH3sYwG2803kcNVew")
SHEET_NAME = os.getenv("SHEET_NAME", "Player_status")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE")

# ========== VERIFICAR TOKEN TWITCH ==========
def verificar_token_twitch(token, client_id, canal):
    """Verifica se o token da Twitch é válido e tem as permissões necessárias."""
    if not token:
        print("❌ Token não disponível")
        return False
    
    if not client_id:
        print("❌ Client ID não disponível")
        return False
    
    try:
        # Verificar identidade do usuário
        url = "https://api.twitch.tv/helix/users"
        headers = {
            "Client-ID": client_id,
            "Authorization": f"Bearer {token}"
        }
        response = requests.get(url, headers=headers)
        
        print(f"🔍 Resposta da API Twitch (verificação de usuário): {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if not data.get("data"):
                print(f"❌ Token válido, mas não retornou dados: {data}")
                return False
                
            username = data["data"][0]["login"]
            print(f"✅ Token é válido para o usuário: {username}")
            
            # Verificar se é o mesmo usuário do canal configurado
            if username.lower() != canal.lower():
                print(f"⚠️ Aviso: O token é para o usuário {username}, mas o canal configurado é {canal}")
            
            # Verificar capacidade de criar enquete (opcional, pode dar erro)
            try:
                broadcaster_id = data["data"][0]["id"]
                url = f"https://api.twitch.tv/helix/polls?broadcaster_id={broadcaster_id}"
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    print("✅ Token tem permissão para gerenciar enquetes")
                else:
                    print(f"⚠️ O token pode não ter permissão para gerenciar enquetes: {response.status_code}")
            except Exception as e:
                print(f"⚠️ Erro ao verificar permissão de enquetes: {e}")
            
            return True
        else:
            error_message = response.text if hasattr(response, 'text') else "Unknown error"
            print(f"❌ Token inválido. Resposta: {error_message}")
            return False
            
    except Exception as e:
        print(f"❌ Erro ao verificar token: {e}")
        print(traceback.format_exc())  # Imprimir stack trace detalhado
        return False

# ========== OBTENDO TOKEN TWITCH ==========
def obter_token_via_refresh():
    try:
        if not REFRESH_TOKEN:
            print("❌ REFRESH_TOKEN não está definido")
            return None
            
        print("🔄 Obtendo novo token via refresh...")
        response = requests.get(REFRESH_API_URL)
        
        # Verificar se a resposta é um JSON válido
        try:
            data = response.json()
        except Exception as e:
            print(f"❌ Erro ao parsear JSON da resposta: {e}")
            print(f"Conteúdo da resposta: {response.text[:100]}...")
            return None

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
        print(traceback.format_exc())  # Imprimir stack trace detalhado
        return None

# Obter token e verificar validade
token_data = obter_token_via_refresh()
if token_data:
    TOKEN = token_data["access_token"]
    NEW_REFRESH_TOKEN = token_data["refresh_token"]  # Salvar para futura atualização
    print(f"🔑 Token de acesso: {TOKEN[:5]}...")
    
    # Verificar se o token é válido
    print("🔍 Verificando token da Twitch...")
    token_valido = verificar_token_twitch(TOKEN, CLIENT_ID, CANAL)
    if not token_valido:
        print("⚠️ O bot pode não funcionar corretamente devido a problemas com o token")
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
        print(f"🔤 Prefixo do bot configurado como: {self.prefix}")
        print(f"🎯 Bot configurado para o canal: {CANAL}")

    async def event_ready(self):
        print(f"✅ Bot {self.nick} conectado ao canal {CANAL}!")
        # Teste para verificar se está realmente conectado
        try:
            # Enviar uma mensagem para você mesmo (como um ping)
            channel = self.get_channel(CANAL)
            if channel:
                await channel.send("🤖 Bot inicializado e pronto para receber comandos!")
                print(f"✅ Mensagem de inicialização enviada para o canal {CANAL}")
            else:
                print(f"❌ Não foi possível obter o canal {CANAL}")
        except Exception as e:
            print(f"❌ Erro ao enviar mensagem de inicialização: {e}")
            print(traceback.format_exc())

    async def event_message(self, message):
        try:
            if message.echo:
                return
            print(f"💬 Mensagem recebida de {message.author.name}: {message.content}")
            
            # Verificar se começa com um comando
            # É um comando direto? (começa com o prefixo)
            if message.content.startswith(self.prefix):
                print(f"📝 Mensagem identificada como comando: {message.content}")
                await self.handle_commands(message)
            else:
                # Verificação alternativa manual (fallback)
                content_lower = message.content.lower()
                if content_lower.startswith("!pergunta"):
                    print("🔍 Detectado comando !pergunta manualmente")
                    await self.pergunta_gemini(message)
                elif content_lower.startswith("!enquete"):
                    print("📊 Detectado comando !enquete manualmente")
                    await self.cmd_enquete(message)
                elif content_lower.startswith("!teste"):
                    print("🧪 Detectado comando !teste manualmente")
                    await message.channel.send(f"✅ Olá {message.author.name}, o bot está funcionando!")
        except Exception as e:
            print(f"❌ Erro ao processar mensagem: {e}")
            print(traceback.format_exc())

    async def event_command_error(self, ctx, error):
        print(f"❌ Erro no comando: {error}")
        if isinstance(error, commands.CommandNotFound):
            print(f"❌ Comando não encontrado: {ctx.message.content}")
        elif isinstance(error, commands.CommandError):
            print(f"❌ Erro ao executar comando: {error}")
        print(traceback.format_exc())

    def obter_broadcaster_id(self):
        """Obtém o ID do streamer (broadcaster) para uso na API da Twitch."""
        url = "https://api.twitch.tv/helix/users"
        headers = {
            "Client-ID": CLIENT_ID,
            "Authorization": f"Bearer {TOKEN}"
        }
        try:
            response = requests.get(url, headers=headers)
            print(f"🔍 Resposta da API Twitch (obter_broadcaster_id): {response.status_code}")
            data = response.json()
            broadcaster_id = data["data"][0]["id"] if "data" in data and data["data"] else None
            if broadcaster_id:
                print(f"✅ Broadcaster ID obtido: {broadcaster_id}")
            else:
                print("❌ Não foi possível obter o Broadcaster ID")
            return broadcaster_id
        except Exception as e:
            print(f"❌ Erro ao obter broadcaster_id: {e}")
            print(traceback.format_exc())
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

            print(f"📤 Enviando requisição para criar enquete: {titulo}")
            print(f"📋 Opções: {opcoes_formatadas}")
            print(f"📋 Body da requisição: {body}")
            
            response = requests.post(url, headers=headers, json=body)
            print(f"🔁 Resposta API Twitch para criar enquete: {response.status_code}")
            print(f"📄 Corpo da resposta: {response.text}")
            
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Erro ao criar enquete: {e}")
            print(traceback.format_exc())
            return False

    @commands.command(name="teste")
    async def cmd_teste(self, ctx):
        print(f"🧪 Comando teste recebido de {ctx.author.name}")
        try:
            await ctx.send(f"✅ Olá {ctx.author.name}, o bot está funcionando!")
            print(f"✅ Resposta do comando teste enviada para {ctx.author.name}")
        except Exception as e:
            print(f"❌ Erro ao responder comando teste: {e}")
            print(traceback.format_exc())

    @commands.command(name="compare")
    async def compare_character(self, ctx):
        print(f"🎮 Comando compare recebido de {ctx.author.name}")
        try:
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
                print(f"❌ Erro ao processar comparação WoW: {e}")
                print(traceback.format_exc())
                await ctx.send(f"Erro ao processar a comparação: {str(e)[:100]}...")
        except Exception as e:
            print(f"❌ Erro geral no comando compare: {e}")
            print(traceback.format_exc())

    @commands.command(name="enquete")
    async def cmd_enquete(self, ctx):
        """
        Comando que permite ao dono do canal criar uma enquete gerada por IA.
        Uso: !enquete tema da enquete
        """
        print(f"📊 Comando enquete recebido de {ctx.author.name}")
        try:
            autor = ctx.author.name.lower()
            canal = CANAL.lower()
            
            # Verificar se quem enviou o comando é o dono do canal
            if autor != canal:
                print(f"⛔ Comando enquete rejeitado: Usuário {autor} não é o dono do canal {canal}")
                await ctx.send(f"⛔ Apenas o dono do canal pode criar enquetes!")
                return
            
            # Verificar se o modelo Gemini está disponível
            if not model:
                print("❌ Modelo Gemini não está disponível para criar enquete")
                await ctx.send("❌ Não foi possível criar a enquete devido a problemas com a IA.")
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
                print(f"🧠 Enviando prompt para o Gemini: {prompt}")
                
                # Consultar a IA para criar uma enquete
                response = model.generate_content(prompt)
                resposta = response.text.strip()
                print(f"✅ Resposta do Gemini: {resposta[:100]}...")
                
                # Processar a resposta para extrair título e opções
                linhas = resposta.splitlines()
                titulo = linhas[0].strip() if linhas else "Enquete Gerada por IA"
                print(f"📋 Título extraído: {titulo}")
                
                # Extrair opções (linhas que começam com traço, asterisco ou número)
                opcoes = []
                for linha in linhas[1:]:
                    linha_limpa = linha.strip()
                    if linha_limpa and (linha_limpa.startswith('-') or 
                                       linha_limpa.startswith('*') or 
                                       linha_limpa.startswith('•') or
                                       (len(linha_limpa) > 1 and linha_limpa[0].isdigit() and linha_limpa[1:2] in [')', '.', ':'])):
                        opcao = linha_limpa.lstrip('-*•0123456789). :').strip()
                        opcoes.append(opcao)
                
                print(f"📋 Opções extraídas: {opcoes}")
                
                # Se não conseguimos extrair pelo menos 2 opções, vamos tentar uma abordagem mais simples
                if len(opcoes) < 2:
                    print("⚠️ Menos de 2 opções extraídas, tentando abordagem alternativa")
                    # Procurar por linhas não vazias depois do título
                    opcoes = [linha.strip() for linha in linhas[1:] if linha.strip()][:5]
                    print(f"📋 Opções alternativas: {opcoes}")
                    
                    # Se ainda não temos opções suficientes, vamos gerar algumas padrão
                    if len(opcoes) < 2:
                        print("⚠️ Ainda sem opções suficientes, gerando opções padrão")
                        opcoes = ["Sim", "Não", "Talvez"]
                
                # Limitar a 5 opções (máximo permitido pela Twitch)
                opcoes = opcoes[:5]
                
                # Criar a enquete
                print("📊 Tentando criar enquete na Twitch...")
                sucesso = self.enviar_enquete(titulo, opcoes)
                
                if sucesso:
                    await ctx.send(f"📊 Enquete criada: {titulo}")
                    print("✅ Enquete criada com sucesso!")
                else:
                    await ctx.send("❌ Falha ao criar a enquete. Verifique se o token tem permissão para gerenciar enquetes (channel:manage:polls).")
                    print("❌ Falha ao criar enquete via API da Twitch")
            
            except Exception as e:
                print(f"❌ Erro ao processar AI para enquete: {e}")
                print(traceback.format_exc())
                await ctx.send("⚠️ Ocorreu um erro ao gerar ou enviar a enquete.")
        
        except Exception as e:
            print(f"❌ Erro geral ao processar comando enquete: {e}")
            print(traceback.format_exc())
            await ctx.send("⚠️ Ocorreu um erro inesperado.")

    @commands.command(name="pergunta")
    async def pergunta_gemini(self, ctx):
        print(f"🔍 Comando pergunta recebido de {ctx.author.name}")
        try:
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

            # Verificar se o modelo Gemini está disponível
            if not model:
                print("❌ Modelo Gemini não está disponível para responder pergunta")
                await ctx.send("❌ O serviço de IA está temporariamente indisponível. Tente novamente mais tarde.")
                return

            try:
                await ctx.send("🤖 Pensando...")
                print(f"🧠 Enviando prompt para o Gemini: {prompt}")
                
                response = model.generate_content(prompt)
                resposta = response.text.strip()
                print(f"✅ Resposta do Gemini: {resposta[:100]}...")

                if not resposta:
                    resposta = "Desculpe, não consegui pensar em nada agora. 😅"

                resposta_formatada = "[IA] " + resposta
                if len(resposta_formatada) > 490:
                    resposta_formatada = resposta_formatada[:490] + "..."

                await ctx.send(resposta_formatada)
                self.cooldown_usuarios[autor] = agora
                print(f"✅ Resposta enviada para {autor}")
                
            except Exception as e:
                print(f"❌ Erro ao gerar resposta com Gemini: {e}")
                print(traceback.format_exc())
                await ctx.send("⚠️ Ocorreu um erro ao consultar a IA. Tente novamente.")
        except Exception as e:
            print(f"❌ Erro geral ao processar comando pergunta: {e}")
            print(traceback.format_exc())

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
        print(traceback.format_exc())

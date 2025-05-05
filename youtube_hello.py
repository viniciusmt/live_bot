import os
import time
from datetime import datetime, timedelta, timezone
import google.generativeai as genai
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import logging
import re

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Carregamento de variáveis de ambiente
load_dotenv()

# Configurações do YouTube
TOKEN_FILE = os.getenv("TOKEN_FILE", "token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
YOUTUBE_VIDEO_ID = os.getenv("YOUTUBE_VIDEO_ID")

# Verificar se o ID do vídeo está definido
if not YOUTUBE_VIDEO_ID:
    logger.warning("⚠️ ID do vídeo do YouTube não está definido. O bot não funcionará corretamente.")
else:
    logger.info(f"ID do vídeo do YouTube configurado: {YOUTUBE_VIDEO_ID}")

# Configuração do Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.error("❌ Chave de API do Gemini não está definida. O bot não funcionará.")
else:
    genai.configure(api_key=GEMINI_API_KEY)
    generation_config = {
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 1024,  # Limitado para respostas mais curtas
    }
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
    )
    logger.info("✅ Modelo Gemini configurado com sucesso")

def get_youtube_service():
    """Autentica e retorna o serviço do YouTube."""
    try:
        if not os.path.exists(TOKEN_FILE):
            logger.error(f"Arquivo de token {TOKEN_FILE} não existe")
            return None
            
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        service = build("youtube", "v3", credentials=creds)
        logger.info("✅ Serviço do YouTube inicializado com sucesso")
        return service
    except Exception as e:
        logger.error(f"❌ Erro ao obter serviço do YouTube: {e}")
        return None

def get_live_chat_id(youtube, video_id):
    """Obtém o ID do chat da live."""
    try:
        if not video_id:
            logger.error("ID do vídeo não fornecido para get_live_chat_id")
            return None
            
        logger.info(f"Buscando chat ID para o vídeo: {video_id}")
        request = youtube.videos().list(
            part="liveStreamingDetails",
            id=video_id
        )
        response = request.execute()
        items = response.get("items", [])
        
        if not items:
            logger.error(f"Nenhum item encontrado para o vídeo {video_id}")
            return None
            
        if "liveStreamingDetails" in items[0]:
            chat_id = items[0]["liveStreamingDetails"].get("activeLiveChatId")
            if chat_id:
                logger.info(f"Chat ID encontrado: {chat_id}")
                return chat_id
            else:
                logger.error("Nenhum activeLiveChatId encontrado nos detalhes da transmissão")
        else:
            logger.error("Nenhum liveStreamingDetails encontrado no vídeo. Talvez não seja uma transmissão ao vivo?")
            
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar chat ID: {e}")
        return None

def limpar_texto(texto):
    """Remove formatação markdown e limita o tamanho do texto."""
    # Remover formatação Markdown
    texto = re.sub(r'\*\*|\*|__|_|##|#|`', '', texto)
    
    # Remover listas com marcadores
    texto = re.sub(r'\n\s*\*\s+', '. ', texto)
    
    # Simplificar quebras de linha
    texto = re.sub(r'\n+', ' ', texto)
    
    # Limitar a 150 caracteres
    if len(texto) > 150:
        texto = texto[:147] + "..."
        
    return texto

def enviar_resposta_youtube(youtube, chat_id, texto, autor=None):
    """Envia mensagem simplificada para o chat."""
    texto_formatado = limpar_texto(texto)
    if autor:
        texto_formatado = f"[IA para {autor}] {texto_formatado}"
    
    try:
        youtube.liveChatMessages().insert(
            part="snippet",
            body={
                "snippet": {
                    "liveChatId": chat_id,
                    "type": "textMessageEvent",
                    "textMessageDetails": {
                        "messageText": texto_formatado
                    }
                }
            }
        ).execute()
        logger.info(f"Mensagem enviada: {texto_formatado[:30]}...")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem: {e}")
        return False

def obter_tempo_atual_da_live(youtube, chat_id):
    """Obtém o timestamp atual da live para ignorar mensagens antigas."""
    try:
        request = youtube.liveChatMessages().list(
            liveChatId=chat_id,
            part="snippet",
            maxResults=1
        )
        response = request.execute()
        if response.get("items"):
            # Pegamos apenas o token da próxima página para começar daqui
            return response.get("nextPageToken")
        return None
    except Exception as e:
        logger.error(f"Erro ao obter tempo atual da live: {e}")
        return None

def monitorar_chat_youtube():
    """Monitora o chat do YouTube e responde a comandos, ignorando mensagens antigas."""
    # Verificar se o ID do vídeo está definido
    video_id = os.getenv("YOUTUBE_VIDEO_ID")
    if not video_id:
        logger.error("ID do vídeo do YouTube não está definido")
        return
    
    logger.info(f"Usando vídeo do YouTube com ID: {video_id}")
    
    youtube = get_youtube_service()
    if not youtube:
        logger.error("Não foi possível autenticar com a API do YouTube")
        return
    
    chat_id = get_live_chat_id(youtube, video_id)
    if not chat_id:
        logger.error("Não foi possível obter o ID do chat ao vivo")
        return
    
    # Importante: Obter o token da página atual para começar a partir daqui
    # Isso evita processar mensagens antigas
    next_page_token = obter_tempo_atual_da_live(youtube, chat_id)
    
    cooldown_usuarios = {}
    tempo_limite = timedelta(seconds=60)
    mensagem_ids_processadas = set()

    logger.info("🎥 Monitorando o chat da live do YouTube (apenas mensagens novas)...")
    logger.info(f"Token de início: {next_page_token}")

    while True:
        try:
            # Obter mensagens do chat a partir do token atual
            request_response = youtube.liveChatMessages().list(
                liveChatId=chat_id,
                part="snippet,authorDetails",
                pageToken=next_page_token
            ).execute()

            # Processar as mensagens recebidas
            for item in request_response.get("items", []):
                msg_id = item["id"]
                if msg_id in mensagem_ids_processadas:
                    continue
                
                mensagem_ids_processadas.add(msg_id)
                autor = item["authorDetails"]["displayName"]
                mensagem = item["snippet"]["displayMessage"]
                agora = datetime.now(timezone.utc)

                # Verificar se é um comando de pergunta
                if mensagem.lower().startswith("!pergunta"):
                    prompt = mensagem.replace("!pergunta", "").strip()

                    if not prompt:
                        enviar_resposta_youtube(youtube, chat_id, 
                            "Envie uma pergunta após o comando. Ex: !pergunta Qual o maior planeta?", 
                            autor)
                        continue

                    if autor in cooldown_usuarios:
                        tempo_restante = (cooldown_usuarios[autor] + tempo_limite) - agora
                        if tempo_restante.total_seconds() > 0:
                            segundos = int(tempo_restante.total_seconds())
                            enviar_resposta_youtube(youtube, chat_id, 
                                f"Aguarde {segundos}s antes de perguntar novamente.", 
                                autor)
                            continue

                    logger.info(f"🧠 {autor} perguntou: {prompt}")
                    try:
                        # Enviar prompt curto explícito para o Gemini
                        prompt_modificado = f"Responda de forma muito breve (máximo de 120 caracteres) e simples: {prompt}"
                        ai_response = model.generate_content(prompt_modificado)
                        
                        # Processar a resposta corretamente
                        resposta = ai_response.text.strip()
                        
                        if not resposta:
                            resposta = "Desculpe, não consegui processar sua pergunta."
                        
                        sucesso = enviar_resposta_youtube(youtube, chat_id, resposta, autor)
                        
                        if sucesso:
                            cooldown_usuarios[autor] = agora
                            logger.info(f"Resposta enviada para {autor}")
                        else:
                            logger.error(f"Falha ao enviar resposta para {autor}")
                            
                    except Exception as e:
                        logger.error(f"❌ Erro ao consultar o Gemini: {e}")
                        try:
                            enviar_resposta_youtube(youtube, chat_id, 
                                "Erro ao processar sua pergunta. Tente novamente.", 
                                autor)
                        except:
                            pass

            # Atualizar o token para a próxima página
            next_page_token = request_response.get("nextPageToken")
            time.sleep(5)  # Aguardar entre as verificações

        except Exception as e:
            logger.error(f"⚠️ Erro ao ler mensagens do chat: {e}")
            time.sleep(10)

if __name__ == "__main__":
    logger.info("Iniciando bot de perguntas para YouTube...")
    monitorar_chat_youtube()

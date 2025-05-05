import os
import threading
import logging
import re
import json
import asyncio
from flask import Flask, jsonify, request
from Bot_Twitch import MeuBot
from youtube_hello import monitorar_chat_youtube
from dotenv import load_dotenv
from keep_alive import KeepAliveService
from utils import setup_logging, check_environment_variables, setup_credentials_files

# Configuração de logging
setup_logging()
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

# Verificar variáveis de ambiente necessárias
required_vars = [
    "GEMINI_API_KEY",
    "TWITCH_CANAL",
    "TWITCH_CLIENT_ID",
    "TWITCH_REFRESH_TOKEN"
]

# Verificação adicional para o YouTube (opcional, já que é independente)
if os.getenv("YOUTUBE_VIDEO_ID"):
    logger.info("Configuração do YouTube detectada - o serviço será iniciado")
else:
    logger.warning("⚠️ YOUTUBE_VIDEO_ID não está definido - o serviço do YouTube NÃO será iniciado")

missing_vars = check_environment_variables(required_vars)
if missing_vars:
    logger.warning(f"⚠️ As seguintes variáveis de ambiente estão ausentes: {', '.join(missing_vars)}")

# Configurar arquivos de credenciais
setup_credentials_files()

# Inicializar o aplicativo Flask
app = Flask(__name__)

# Variáveis para armazenar threads
twitch_thread = None
youtube_thread = None
twitch_bot = None
keep_alive_service = None

# Status para monitoramento
bot_status = {
    "twitch": "stopped",
    "youtube": "stopped",
    "keep_alive": "stopped"
}

def verificar_arquivos_credenciais():
    """Verifica se os arquivos de credenciais necessários existem e são válidos."""
    files_to_check = {
        "TOKEN_FILE": os.getenv("TOKEN_FILE", "token.json"),
        "CLIENT_SECRETS_FILE": os.getenv("CLIENT_SECRETS_FILE", "client_secret.json"),
        "CREDENTIALS_FILE": os.getenv("CREDENTIALS_FILE", "credentials.json")
    }
    
    for name, path in files_to_check.items():
        if os.path.exists(path):
            file_size = os.path.getsize(path)
            logger.info(f"✅ Arquivo {name} ({path}) existe com tamanho {file_size} bytes")
            
            # Verificar se é um JSON válido
            try:
                with open(path, 'r') as f:
                    json.loads(f.read())
                logger.info(f"✅ Arquivo {name} contém JSON válido")
            except Exception as e:
                logger.error(f"❌ Arquivo {name} não contém JSON válido: {e}")
        else:
            logger.error(f"❌ Arquivo {name} ({path}) não existe")
    
    # Verificar variáveis de ambiente críticas
    env_vars = ["GEMINI_API_KEY", "TWITCH_CANAL", "TWITCH_CLIENT_ID", 
                "TWITCH_REFRESH_TOKEN", "YOUTUBE_VIDEO_ID"]
    
    for var in env_vars:
        value = os.getenv(var)
        if value:
            # Mostrar apenas os primeiros caracteres para segurança
            display_value = value[:5] + "..." if len(value) > 5 else "[vazio]"
            logger.info(f"✅ Variável {var} definida como {display_value}")
        else:
            logger.warning(f"⚠️ Variável {var} não definida")

def iniciar_bot_twitch():
    """Função para iniciar o bot da Twitch em uma thread separada"""
    global bot_status, twitch_bot
    
    try:
        logger.info("🎮 Iniciando bot da Twitch...")
        # Criar um novo event loop para esta thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        twitch_bot = MeuBot()
        bot_status["twitch"] = "running"
        twitch_bot.run()
    except Exception as e:
        logger.error(f"❌ Erro ao iniciar bot da Twitch: {e}")
        bot_status["twitch"] = f"error: {str(e)}"

def iniciar_bot_youtube():
    """Função para iniciar o monitoramento do YouTube em uma thread separada"""
    global bot_status
    
    # Verificar se YOUTUBE_VIDEO_ID está definido - se não estiver, não iniciar
    if not os.getenv("YOUTUBE_VIDEO_ID"):
        logger.error("❌ YOUTUBE_VIDEO_ID não está definido - o serviço do YouTube não será iniciado")
        bot_status["youtube"] = "disabled"
        return
        
    try:
        logger.info("🎥 Iniciando monitoramento do YouTube...")
        bot_status["youtube"] = "running"
        monitorar_chat_youtube()
    except Exception as e:
        logger.error(f"❌ Erro ao iniciar monitoramento do YouTube: {e}")
        bot_status["youtube"] = f"error: {str(e)}"

@app.route('/')
def home():
    """Rota principal para verificar se o serviço está funcionando"""
    return jsonify({
        "status": "online",
        "bots": bot_status,
        "environment": "render" if os.getenv("RENDER_EXTERNAL_HOSTNAME") else "local"
    })

@app.route('/update_youtube', methods=['POST'])
def update_youtube_id():
    """Rota para atualizar o ID do vídeo do YouTube e reiniciar o bot do YouTube"""
    global youtube_thread, bot_status
    
    # Verificar autenticação simples com chave de API
    auth_key = request.headers.get('X-API-Key')
    expected_key = os.getenv('API_KEY')
    
    if not auth_key or auth_key != expected_key:
        return jsonify({"error": "Não autorizado"}), 401
    
    # Obter o novo ID do vídeo do corpo da requisição
    data = request.json
    if not data or 'video_id' not in data:
        return jsonify({"error": "ID do vídeo não fornecido"}), 400
    
    new_video_id = data['video_id']
    
    # Validar o ID do vídeo (formatação básica)
    if not re.match(r'^[a-zA-Z0-9_-]{11}$', new_video_id):
        return jsonify({"error": "Formato de ID de vídeo inválido"}), 400
    
    # Atualizar a variável de ambiente
    os.environ['YOUTUBE_VIDEO_ID'] = new_video_id
    logger.info(f"🔄 ID do vídeo do YouTube atualizado para: {new_video_id}")
    
    # Se o bot do YouTube estiver rodando, vamos tentar reiniciá-lo
    if bot_status["youtube"] == "running" or bot_status["youtube"] == "starting":
        bot_status["youtube"] = "restarting"
        
        # Iniciar uma nova thread para o bot do YouTube
        youtube_thread = threading.Thread(target=iniciar_bot_youtube)
        youtube_thread.daemon = True
        youtube_thread.start()
        
        return jsonify({
            "message": f"ID do vídeo atualizado para {new_video_id} e bot do YouTube está sendo reiniciado",
            "status": bot_status
        })
    else:
        # Se o bot do YouTube não estiver rodando, iniciá-lo
        bot_status["youtube"] = "starting"
        youtube_thread = threading.Thread(target=iniciar_bot_youtube)
        youtube_thread.daemon = True
        youtube_thread.start()
        
        return jsonify({
            "message": f"ID do vídeo atualizado para {new_video_id} e bot do YouTube está sendo iniciado",
            "status": bot_status
        })
    
@app.route('/start')
def start_bots():
    """Rota para iniciar os bots independentemente"""
    global twitch_thread, youtube_thread, bot_status, keep_alive_service
    
    # Verificar arquivos de credenciais antes de iniciar
    verificar_arquivos_credenciais()
    
    service = request.args.get("service", "all")
    start_result = {"message": "Iniciando bots solicitados", "details": {}}
    
    # Iniciar bot da Twitch se não estiver rodando
    if bot_status["twitch"] != "running" and service in ["all", "twitch"]:
        if missing_vars := check_environment_variables(["GEMINI_API_KEY", "TWITCH_CANAL", "TWITCH_CLIENT_ID", "TWITCH_REFRESH_TOKEN"]):
            start_result["details"]["twitch"] = f"Não iniciado - faltam variáveis: {', '.join(missing_vars)}"
        else:
            twitch_thread = threading.Thread(target=iniciar_bot_twitch)
            twitch_thread.daemon = True
            twitch_thread.start()
            bot_status["twitch"] = "starting"
            start_result["details"]["twitch"] = "Iniciando"
    else:
        start_result["details"]["twitch"] = f"Status atual: {bot_status['twitch']}"
    
    # Iniciar bot do YouTube se não estiver rodando e YOUTUBE_VIDEO_ID estiver definido
    if bot_status["youtube"] != "running" and service in ["all", "youtube"]:
        if not os.getenv("YOUTUBE_VIDEO_ID"):
            start_result["details"]["youtube"] = "Não iniciado - YOUTUBE_VIDEO_ID não definido"
        elif missing_vars := check_environment_variables(["GEMINI_API_KEY"]):
            start_result["details"]["youtube"] = f"Não iniciado - faltam variáveis: {', '.join(missing_vars)}"
        else:
            youtube_thread = threading.Thread(target=iniciar_bot_youtube)
            youtube_thread.daemon = True
            youtube_thread.start()
            bot_status["youtube"] = "starting"
            start_result["details"]["youtube"] = "Iniciando"
    else:
        start_result["details"]["youtube"] = f"Status atual: {bot_status['youtube']}"
    
    # Iniciar serviço de keep-alive para manter o aplicativo ativo
    if bot_status["keep_alive"] != "running":
        keep_alive_service = KeepAliveService(interval_minutes=10)
        keep_alive_service.start()
        bot_status["keep_alive"] = "running"
        start_result["details"]["keep_alive"] = "Iniciado"
    else:
        start_result["details"]["keep_alive"] = f"Status atual: {bot_status['keep_alive']}"
    
    return jsonify(start_result)

@app.route('/start_twitch')
def start_twitch_only():
    """Rota para iniciar apenas o bot da Twitch"""
    request.args = {"service": "twitch"}
    return start_bots()

@app.route('/start_youtube')
def start_youtube_only():
    """Rota para iniciar apenas o bot do YouTube"""
    request.args = {"service": "youtube"}
    return start_bots()

@app.route('/stop')
def stop_bots():
    """Rota para parar os bots (não implementável diretamente, reinicie o serviço para parar)"""
    global keep_alive_service, bot_status
    
    # Podemos pelo menos parar o serviço de keep-alive
    if keep_alive_service and bot_status["keep_alive"] == "running":
        keep_alive_service.stop()
        bot_status["keep_alive"] = "stopped"
    
    return jsonify({
        "message": "Para parar os bots completamente, reinicie o serviço no Render",
        "status": bot_status
    })

@app.route('/status')
def status():
    """Rota para verificar o status dos bots"""
    return jsonify({
        "bots": bot_status,
        "uptime": "Disponível no Render Dashboard"
    })

@app.route('/debug')
def debug_info():
    """Rota para obter informações de debug do sistema"""
    env_info = {}
    
    # Coletar informações de ambiente (ocultando valores sensíveis)
    for key, value in os.environ.items():
        if key in ["GEMINI_API_KEY", "TWITCH_CLIENT_ID", "TWITCH_REFRESH_TOKEN", 
                  "BLIZZARD_CLIENT_SECRET", "API_KEY"]:
            env_info[key] = f"{value[:5]}..." if value else "[não definido]"
        else:
            env_info[key] = value
    
    # Verificar arquivos existentes no diretório
    try:
        files = os.listdir(".")
    except:
        files = ["Erro ao listar arquivos"]
    
    return jsonify({
        "status": bot_status,
        "environment": env_info,
        "files": files
    })

@app.route('/restart', methods=['POST'])
def restart_bot():
    """Rota para reiniciar um bot específico (requer autenticação básica)"""
    auth_key = request.headers.get('X-API-Key')
    expected_key = os.getenv('API_KEY')
    
    if not auth_key or auth_key != expected_key:
        return jsonify({"error": "Não autorizado"}), 401
    
    # Obter o nome do bot a ser reiniciado (all, twitch, youtube)
    bot_name = request.args.get('bot', 'all')
    
    # Reset dos status
    if bot_name == 'all' or bot_name == 'twitch':
        bot_status["twitch"] = "restarting"
    
    if bot_name == 'all' or bot_name == 'youtube':
        bot_status["youtube"] = "restarting"
    
    # Iniciar novas threads para os bots solicitados
    result = {"message": f"Solicitação de reinício recebida para: {bot_name}", "status": {}}
    
    if bot_name == 'all' or bot_name == 'twitch':
        twitch_thread = threading.Thread(target=iniciar_bot_twitch)
        twitch_thread.daemon = True
        twitch_thread.start()
        result["status"]["twitch"] = "reiniciando"
    
    if bot_name == 'all' or bot_name == 'youtube':
        if os.getenv("YOUTUBE_VIDEO_ID"):
            youtube_thread = threading.Thread(target=iniciar_bot_youtube)
            youtube_thread.daemon = True
            youtube_thread.start()
            result["status"]["youtube"] = "reiniciando"
        else:
            result["status"]["youtube"] = "desativado (YOUTUBE_VIDEO_ID não definido)"
    
    return jsonify(result)

if __name__ == "__main__":
    # Iniciar os bots automaticamente ao iniciar o aplicativo
    # Podemos iniciar os bots de forma independente
    
    # Iniciar Twitch Bot (se todas as variáveis necessárias estiverem definidas)
    if not check_environment_variables(["GEMINI_API_KEY", "TWITCH_CANAL", "TWITCH_CLIENT_ID", "TWITCH_REFRESH_TOKEN"]):
        logger.info("Iniciando Bot da Twitch automaticamente...")
        twitch_thread = threading.Thread(target=iniciar_bot_twitch)
        twitch_thread.daemon = True
        twitch_thread.start()
        bot_status["twitch"] = "starting"
    else:
        logger.warning("⚠️ Bot da Twitch não iniciado automaticamente - variáveis de ambiente ausentes")
    
    # Iniciar YouTube Bot (se o YOUTUBE_VIDEO_ID estiver definido)
    if os.getenv("YOUTUBE_VIDEO_ID") and not check_environment_variables(["GEMINI_API_KEY"]):
        logger.info("Iniciando Bot do YouTube automaticamente...")
        youtube_thread = threading.Thread(target=iniciar_bot_youtube)
        youtube_thread.daemon = True
        youtube_thread.start()
        bot_status["youtube"] = "starting"
    else:
        logger.warning("⚠️ Bot do YouTube não iniciado automaticamente - YOUTUBE_VIDEO_ID ou GEMINI_API_KEY ausente")
    
    # Iniciar serviço de keep-alive
    logger.info("Iniciando serviço keep-alive...")
    keep_alive_service = KeepAliveService(interval_minutes=10)
    keep_alive_service.start()
    bot_status["keep_alive"] = "running"
    
    # Iniciar o servidor Flask
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

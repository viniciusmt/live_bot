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
    "TWITCH_REFRESH_TOKEN",
    "YOUTUBE_VIDEO_ID"
]

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
            logger.error(f"❌ Variável {var} não definida")

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
    # (Na prática, isso matará a thread atual e iniciará uma nova)
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
        return jsonify({
            "message": f"ID do vídeo atualizado para {new_video_id}",
            "note": "Bot do YouTube não está rodando. Use /start para iniciá-lo.",
            "status": bot_status
        })
    
@app.route('/start')
def start_bots():
    """Rota para iniciar os bots"""
    global twitch_thread, youtube_thread, bot_status, keep_alive_service
    
    # Verificar arquivos de credenciais antes de iniciar
    verificar_arquivos_credenciais()
    
    # Iniciar bot da Twitch se não estiver rodando
    if bot_status["twitch"] != "running":
        twitch_thread = threading.Thread(target=iniciar_bot_twitch)
        twitch_thread.daemon = True
        twitch_thread.start()
        bot_status["twitch"] = "starting"
    
    # Iniciar bot do YouTube se não estiver rodando
    if bot_status["youtube"] != "running":
        youtube_thread = threading.Thread(target=iniciar_bot_youtube)
        youtube_thread.daemon = True
        youtube_thread.start()
        bot_status["youtube"] = "starting"
    
    # Iniciar serviço de keep-alive para manter o aplicativo ativo
    if bot_status["keep_alive"] != "running":
        keep_alive_service = KeepAliveService(interval_minutes=10)
        keep_alive_service.start()
        bot_status["keep_alive"] = "running"
    
    return jsonify({
        "message": "Bots iniciados",
        "status": bot_status
    })

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
    
    bot_name = request.args.get('bot', 'all')
    
    # Código para reiniciar bots específicos aqui
    # (Não implementado completamente - requereria lógica para encerrar threads)
    
    return jsonify({
        "message": f"Solicitação de reinício recebida para: {bot_name}",
        "status": "pending"
    })

if __name__ == "__main__":
    # Iniciar os bots automaticamente ao iniciar o aplicativo
    start_bots()
    
    # Iniciar o servidor Flask
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

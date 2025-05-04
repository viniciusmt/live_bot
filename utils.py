import os
import time
import requests
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def setup_logging(log_level=logging.INFO):
    """Configura o sistema de logging."""
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def save_file_to_disk(filename, content, is_binary=False):
    """
    Salva um arquivo no sistema de arquivos do Render.
    Útil para salvar arquivos de credenciais no ambiente.
    """
    mode = 'wb' if is_binary else 'w'
    with open(filename, mode) as f:
        f.write(content)
    logger.info(f"✅ Arquivo {filename} salvo com sucesso")

def check_environment_variables(required_vars):
    """
    Verifica se todas as variáveis de ambiente necessárias estão definidas.
    Retorna uma lista de variáveis ausentes.
    """
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.warning(f"⚠️ Variáveis de ambiente ausentes: {', '.join(missing_vars)}")
    else:
        logger.info("✅ Todas as variáveis de ambiente necessárias estão definidas")
    
    return missing_vars

def keep_alive():
    """
    Função que pode ser usada para manter o serviço ativo no Render.
    Pode ser chamada periodicamente em uma thread separada.
    """
    server_url = os.getenv("SERVER_URL")
    if not server_url:
        server_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}"
    
    try:
        response = requests.get(f"{server_url}/")
        if response.status_code == 200:
            logger.debug(f"Keep-alive ping enviado em {datetime.now().isoformat()}")
            return True
        else:
            logger.warning(f"Keep-alive falhou com status code {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Erro no keep-alive: {e}")
        return False

def obter_token_via_refresh(refresh_api_url):
    """
    Obtém um novo token de acesso da Twitch usando o token de atualização.
    """
    try:
        logger.info("🔄 Obtendo novo token via refresh...")
        response = requests.get(refresh_api_url)
        data = response.json()

        if response.status_code == 200 and "token" in data and "refresh" in data:
            logger.info("✅ Novo token obtido com sucesso!")
            return {
                "access_token": data["token"],
                "refresh_token": data["refresh"]
            }
        else:
            logger.error(f"❌ Erro ao obter novo token: {data}")
            return None
    except Exception as e:
        logger.error(f"⚠️ Exceção ao obter token: {e}")
        return None

def setup_credentials_files():
    """
    Verifica e configura os arquivos de credenciais necessários.
    Esta função pode ser usada para criar arquivos temporários 
    com conteúdo de variáveis de ambiente no Render.
    """
    # YouTube token file
    token_content = os.getenv("YOUTUBE_TOKEN_CONTENT")
    token_file = os.getenv("TOKEN_FILE", "token.json")
    if token_content:
        try:
            save_file_to_disk(token_file, token_content)
        except Exception as e:
            logger.error(f"Erro ao salvar arquivo de token do YouTube: {e}")
    
    # Google Sheets credentials
    credentials_content = os.getenv("GOOGLE_CREDENTIALS_CONTENT")
    credentials_file = os.getenv("CREDENTIALS_FILE", "credentials.json")
    if credentials_content:
        try:
            save_file_to_disk(credentials_file, credentials_content)
        except Exception as e:
            logger.error(f"Erro ao salvar arquivo de credenciais do Google: {e}")
    
    # Client secrets file
    client_secrets_content = os.getenv("CLIENT_SECRETS_CONTENT")
    client_secrets_file = os.getenv("CLIENT_SECRETS_FILE", "client_secret.json")
    if client_secrets_content:
        try:
            save_file_to_disk(client_secrets_file, client_secrets_content)
        except Exception as e:
            logger.error(f"Erro ao salvar arquivo de secrets do cliente: {e}")
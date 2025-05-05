import os
import time
import json
import requests
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

def setup_credentials_files():
    """
    Configura os arquivos de credenciais necessários a partir das variáveis de ambiente.
    """
    # Configuração do arquivo de credenciais do cliente (client_secret.json)
    client_secret_content = os.getenv("CLIENT_SECRET_JSON")
    client_secret_file = os.getenv("CLIENT_SECRETS_FILE", "client_secret.json")
    
    if client_secret_content:
        try:
            # Validar se é um JSON válido
            try:
                json_content = json.loads(client_secret_content)
                # Se for um JSON válido, salvar no formato correto
                save_file_to_disk(client_secret_file, json.dumps(json_content, indent=2))
                logger.info(f"✅ Arquivo de client secret salvo como {client_secret_file}")
            except json.JSONDecodeError:
                # Se não for um JSON válido, salvar como está (pode ser um texto escapado)
                save_file_to_disk(client_secret_file, client_secret_content)
                logger.warning(f"⚠️ Conteúdo de CLIENT_SECRET_JSON não é um JSON válido, salvando como texto")
        except Exception as e:
            logger.error(f"❌ Erro ao salvar arquivo de client secret: {e}")
    else:
        logger.warning(f"⚠️ CLIENT_SECRET_JSON não está definido, o arquivo {client_secret_file} não será criado")
    
    # Configuração do arquivo de token do YouTube
    token_content = os.getenv("YOUTUBE_TOKEN_CONTENT")
    token_file = os.getenv("TOKEN_FILE", "token.json")
    if token_content:
        try:
            # Validar se é um JSON válido
            try:
                json_content = json.loads(token_content)
                # Se for um JSON válido, salvar no formato correto
                save_file_to_disk(token_file, json.dumps(json_content, indent=2))
            except json.JSONDecodeError:
                # Se não for um JSON válido, salvar como está
                save_file_to_disk(token_file, token_content)
                logger.warning(f"⚠️ Conteúdo de YOUTUBE_TOKEN_CONTENT não é um JSON válido, salvando como texto")
            logger.info(f"✅ Arquivo de token do YouTube salvo como {token_file}")
        except Exception as e:
            logger.error(f"❌ Erro ao salvar arquivo de token do YouTube: {e}")
    else:
        logger.warning(f"⚠️ YOUTUBE_TOKEN_CONTENT não está definido, o arquivo {token_file} não será criado")
    
    # Configuração do arquivo de credenciais do Google
    credentials_content = os.getenv("GOOGLE_CREDENTIALS_CONTENT")
    credentials_file = os.getenv("CREDENTIALS_FILE", "credentials.json")
    if credentials_content:
        try:
            # Validar se é um JSON válido
            try:
                json_content = json.loads(credentials_content)
                # Se for um JSON válido, salvar no formato correto
                save_file_to_disk(credentials_file, json.dumps(json_content, indent=2))
            except json.JSONDecodeError:
                # Se não for um JSON válido, salvar como está
                save_file_to_disk(credentials_file, credentials_content)
                logger.warning(f"⚠️ Conteúdo de GOOGLE_CREDENTIALS_CONTENT não é um JSON válido, salvando como texto")
            logger.info(f"✅ Arquivo de credenciais do Google salvo como {credentials_file}")
        except Exception as e:
            logger.error(f"❌ Erro ao salvar arquivo de credenciais do Google: {e}")
    else:
        logger.warning(f"⚠️ GOOGLE_CREDENTIALS_CONTENT não está definido, o arquivo {credentials_file} não será criado")

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

import re
import os
import requests
import logging
from dotenv import load_dotenv

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

def extract_video_id(url):
    """
    Extrai o ID do vídeo de uma URL do YouTube.
    Funciona com vários formatos de URL, incluindo:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/live/VIDEO_ID
    """
    # Padrão para URLs de vídeo padrão (youtube.com/watch?v=ID)
    pattern1 = r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    # Padrão para URLs de transmissão ao vivo (youtube.com/live/ID)
    pattern2 = r'youtube\.com\/live\/([a-zA-Z0-9_-]{11})'
    # Padrão para IDs diretos (se já for apenas o ID)
    pattern3 = r'^[a-zA-Z0-9_-]{11}$'
    
    # Tentar extrair usando os diferentes padrões
    match1 = re.search(pattern1, url)
    if match1:
        return match1.group(1)
    
    match2 = re.search(pattern2, url)
    if match2:
        return match2.group(1)
    
    match3 = re.search(pattern3, url)
    if match3:
        return url
    
    return None

def update_youtube_id(new_id_or_url, api_url=None, api_key=None):
    """
    Atualiza o ID do vídeo do YouTube chamando a API do serviço.
    
    Args:
        new_id_or_url: ID do vídeo ou URL completa do YouTube
        api_url: URL base da API (ex: https://seu-app.onrender.com)
        api_key: Chave de API para autenticação
    
    Returns:
        Tuple (sucesso: bool, mensagem: str)
    """
    # Extrair o ID do vídeo se for uma URL
    video_id = extract_video_id(new_id_or_url)
    if not video_id:
        return False, f"ID de vídeo não encontrado em: {new_id_or_url}"
    
    # Se não for fornecida uma URL de API, usar variáveis de ambiente ou padrão
    if not api_url:
        api_url = os.getenv("SERVER_URL", "http://localhost:5000")
    
    # Se não for fornecida uma chave de API, usar a variável de ambiente
    if not api_key:
        api_key = os.getenv("API_KEY")
        if not api_key:
            return False, "Chave de API não encontrada"
    
    # Construir a URL completa
    update_url = f"{api_url}/update_youtube"
    
    # Definir cabeçalhos de autenticação
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key
    }
    
    # Preparar os dados
    data = {
        "video_id": video_id
    }
    
    try:
        # Fazer a requisição para atualizar o ID
        response = requests.post(update_url, json=data, headers=headers)
        
        # Verificar se a requisição foi bem-sucedida
        if response.status_code == 200:
            result = response.json()
            return True, f"Atualizado com sucesso! {result.get('message', '')}"
        else:
            return False, f"Erro {response.status_code}: {response.text}"
    
    except Exception as e:
        return False, f"Erro ao fazer requisição: {e}"

if __name__ == "__main__":
    import sys
    
    # Se for chamado diretamente, usar argumentos de linha de comando
    if len(sys.argv) < 2:
        print("Uso: python youtube_helper.py <URL_OU_ID_DO_VIDEO> [API_URL] [API_KEY]")
        sys.exit(1)
    
    # Coletar argumentos
    video_url_or_id = sys.argv[1]
    api_url = sys.argv[2] if len(sys.argv) > 2 else None
    api_key = sys.argv[3] if len(sys.argv) > 3 else None
    
    # Extrair e mostrar o ID
    video_id = extract_video_id(video_url_or_id)
    if video_id:
        print(f"ID do vídeo extraído: {video_id}")
    else:
        print(f"Não foi possível extrair um ID válido de: {video_url_or_id}")
        sys.exit(1)
    
    # Se fornecida uma URL de API, tentar atualizar
    if api_url:
        success, message = update_youtube_id(video_id, api_url, api_key)
        if success:
            print(f"✅ {message}")
        else:
            print(f"❌ {message}")
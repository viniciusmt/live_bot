#!/usr/bin/env python
"""
Script de configuração para ajudar a gerar os arquivos de configuração necessários
e converter para o formato das variáveis de ambiente do Render.

Este script facilita:
1. Transformar arquivos JSON em variáveis de ambiente para Render
2. Testar as credenciais
3. Extrair o ID correto de um vídeo do YouTube

Uso: python helper_setup.py
"""

import os
import json
import base64
import re
import argparse
from dotenv import load_dotenv
import requests

# Carrega variáveis de ambiente existentes
load_dotenv()

def encode_file_to_base64(filepath):
    """Converte o conteúdo de um arquivo para base64."""
    try:
        with open(filepath, 'rb') as file:
            content = file.read()
            encoded = base64.b64encode(content).decode('utf-8')
            return encoded
    except Exception as e:
        print(f"Erro ao codificar arquivo {filepath}: {e}")
        return None

def file_to_env_var(filepath, var_name):
    """Converte o conteúdo do arquivo para uma variável de ambiente."""
    try:
        with open(filepath, 'r') as file:
            content = file.read()
            # Remove quebras de linha e formata como string JSON
            content_formatted = json.dumps(json.loads(content))
            print(f"{var_name}='{content_formatted}'")
            return content_formatted
    except Exception as e:
        print(f"Erro ao processar arquivo {filepath}: {e}")
        return None

def extract_youtube_id(url):
    """Extrai o ID do vídeo do YouTube de uma URL."""
    # Padrões para diferentes formatos de URL do YouTube
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',  # URLs padrão
        r'youtube\.com\/live\/([a-zA-Z0-9_-]{11})',                    # URLs de transmissão ao vivo
        r'^[a-zA-Z0-9_-]{11}$'                                         # Apenas o ID
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def test_twitch_token(client_id, refresh_token):
    """Testa se o token da Twitch é válido."""
    refresh_api_url = f"https://twitchtokengenerator.com/api/refresh/{refresh_token}"
    
    try:
        response = requests.get(refresh_api_url)
        data = response.json()
        
        if response.status_code == 200 and "token" in data and "refresh" in data:
            print(f"✅ Token da Twitch válido! Novo token: {data['token'][:5]}...")
            return True
        else:
            print(f"❌ Erro ao validar token da Twitch: {data}")
            return False
    except Exception as e:
        print(f"⚠️ Exceção ao obter token: {e}")
        return False

def validate_gemini_api_key(api_key):
    """Verifica se a chave de API do Gemini é válida."""
    import google.generativeai as genai
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content("Hello!")
        
        if response and response.text:
            print(f"✅ Chave de API do Gemini válida! Resposta: {response.text[:20]}...")
            return True
        else:
            print("❌ Erro ao validar chave do Gemini: resposta vazia")
            return False
    except Exception as e:
        print(f"❌ Erro ao validar chave do Gemini: {e}")
        return False

def generate_env_file():
    """Gera um arquivo .env com todas as variáveis configuradas."""
    variables = {
        "GEMINI_API_KEY": input("Digite sua chave de API do Gemini: "),
        "TWITCH_CANAL": input("Digite o nome do canal da Twitch: "),
        "TWITCH_CLIENT_ID": input("Digite o Client ID da Twitch: "),
        "TWITCH_REFRESH_TOKEN": input("Digite o Refresh Token da Twitch: "),
        "YOUTUBE_VIDEO_ID": input("Digite o ID ou URL do vídeo do YouTube: "),
        "API_KEY": input("Crie uma chave de API para administração (pode ser qualquer string): ")
    }
    
    # Extrai o ID do YouTube se for uma URL
    if "youtube.com" in variables["YOUTUBE_VIDEO_ID"] or "youtu.be" in variables["YOUTUBE_VIDEO_ID"]:
        youtube_id = extract_youtube_id(variables["YOUTUBE_VIDEO_ID"])
        if youtube_id:
            print(f"ID do YouTube extraído: {youtube_id}")
            variables["YOUTUBE_VIDEO_ID"] = youtube_id
    
    # Arquivos JSON
    token_file = input("Caminho para o arquivo token.json (deixe em branco para pular): ")
    if token_file and os.path.exists(token_file):
        variables["YOUTUBE_TOKEN_CONTENT"] = file_to_env_var(token_file, "YOUTUBE_TOKEN_CONTENT")
    
    client_secret_file = input("Caminho para o arquivo client_secret.json (deixe em branco para pular): ")
    if client_secret_file and os.path.exists(client_secret_file):
        variables["CLIENT_SECRET_JSON"] = file_to_env_var(client_secret_file, "CLIENT_SECRET_JSON")
    
    credentials_file = input("Caminho para o arquivo credentials.json (deixe em branco para pular): ")
    if credentials_file and os.path.exists(credentials_file):
        variables["GOOGLE_CREDENTIALS_CONTENT"] = file_to_env_var(credentials_file, "GOOGLE_CREDENTIALS_CONTENT")
    
    # Gerar o arquivo .env
    with open(".env", "w") as env_file:
        for key, value in variables.items():
            if value:  # Só adiciona se tiver valor
                env_file.write(f"{key}={value}\n")
    
    print("\n✅ Arquivo .env gerado com sucesso!")
    
    # Testar credenciais
    if "GEMINI_API_KEY" in variables and variables["GEMINI_API_KEY"]:
        validate_gemini_api_key(variables["GEMINI_API_KEY"])
    
    if "TWITCH_CLIENT_ID" in variables and "TWITCH_REFRESH_TOKEN" in variables:
        test_twitch_token(variables["TWITCH_CLIENT_ID"], variables["TWITCH_REFRESH_TOKEN"])

def main():
    parser = argparse.ArgumentParser(description="Configurador para o Bot Twitch/YouTube")
    parser.add_argument("--generate-env", action="store_true", help="Gerar arquivo .env interativamente")
    parser.add_argument("--encode-file", type=str, help="Codificar arquivo para base64")
    parser.add_argument("--file-to-env", type=str, help="Converter arquivo JSON para variável de ambiente")
    parser.add_argument("--extract-youtube-id", type=str, help="Extrair ID do YouTube de uma URL")
    
    args = parser.parse_args()
    
    if args.generate_env:
        generate_env_file()
    elif args.encode_file:
        encoded = encode_file_to_base64(args.encode_file)
        if encoded:
            print(encoded)
    elif args.file_to_env:
        var_name = input("Digite o nome da variável de ambiente: ")
        file_to_env_var(args.file_to_env, var_name)
    elif args.extract_youtube_id:
        youtube_id = extract_youtube_id(args.extract_youtube_id)
        if youtube_id:
            print(f"ID extraído: {youtube_id}")
        else:
            print("Não foi possível extrair o ID do YouTube.")
    else:
        # Se nenhum argumento for fornecido, mostra o menu interativo
        print("=== Configurador do Bot Twitch/YouTube ===")
        print("1. Gerar arquivo .env")
        print("2. Codificar arquivo para base64")
        print("3. Converter arquivo JSON para variável de ambiente")
        print("4. Extrair ID do YouTube de uma URL")
        
        choice = input("Escolha uma opção (1-4): ")
        
        if choice == "1":
            generate_env_file()
        elif choice == "2":
            filepath = input("Digite o caminho do arquivo: ")
            encoded = encode_file_to_base64(filepath)
            if encoded:
                print(encoded)
        elif choice == "3":
            filepath = input("Digite o caminho do arquivo JSON: ")
            var_name = input("Digite o nome da variável de ambiente: ")
            file_to_env_var(filepath, var_name)
        elif choice == "4":
            url = input("Digite a URL do YouTube: ")
            youtube_id = extract_youtube_id(url)
            if youtube_id:
                print(f"ID extraído: {youtube_id}")
            else:
                print("Não foi possível extrair o ID do YouTube.")
        else:
            print("Opção inválida.")

if __name__ == "__main__":
    main()

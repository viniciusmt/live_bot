import os
import requests
import pandas as pd
import re
from unidecode import unidecode
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

# Carregar variáveis de ambiente do arquivo .env
load_dotenv(r"C:\Users\Vinicius\Projetos\bot_twitch\.env")

def get_access_token(client_id, client_secret, region="us"):
    """Autentica na API da Blizzard e retorna um token de acesso."""
    auth_url = f"https://{region}.battle.net/oauth/token"
    response = requests.post(auth_url, data={"grant_type": "client_credentials"}, auth=(client_id, client_secret))
    response.raise_for_status()
    return response.json().get("access_token")

def clean_name(name):
    """Remove acentos e formata o nome para slug."""
    return re.sub(r"[^a-z0-9]+", "-", unidecode(name).lower()).strip("-")

def get_character_data(region, realm_slug, character_name, token):
    """Obtém informações gerais de um personagem."""
    url = f"https://{region}.api.blizzard.com/profile/wow/character/{realm_slug}/{character_name}"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"namespace": "profile-us", "locale": "en_US"}
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        return {
            "Character Name": data.get("name"),
            "Realm": data.get("realm", {}).get("name"),
            "Level": data.get("level"),
            "Gender": data.get("gender", {}).get("name"),
            "Faction": data.get("faction", {}).get("name"),
            "Race": data.get("race", {}).get("name"),
            "Class": data.get("character_class", {}).get("name"),
            "Specialization": data.get("active_spec", {}).get("name"),
            "Title": data.get("active_title", {}).get("name"),
            "Achievement Points": data.get("achievement_points", 0),
            "Average Item Level": data.get("average_item_level", 0),
            "Equipped Item Level": data.get("equipped_item_level", 0),
            "Last Login": data.get("last_login_timestamp"),
            "Guild Name": data.get("guild", {}).get("name", "N/A"),
            "Realm Slug": realm_slug
        }
    print(f"Erro ao obter dados do personagem {character_name}: {response.status_code}")
    return None

def get_character_statistics(region, realm_slug, character_name, token):
    """Obtém estatísticas detalhadas do personagem."""
    url = f"https://{region}.api.blizzard.com/profile/wow/character/{realm_slug}/{character_name}/statistics"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"namespace": "profile-us", "locale": "en_US"}
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        return {
            "Health": data.get("health", 0),
            "Power": data.get("power", 0),
            "Power Type": data.get("power_type", {}).get("name", "N/A"),
            "Strength": data.get("strength", {}).get("effective", 0),
            "Agility": data.get("agility", {}).get("effective", 0),
            "Intellect": data.get("intellect", {}).get("effective", 0),
            "Stamina": data.get("stamina", {}).get("effective", 0),
            "Armor": data.get("armor", {}).get("effective", 0),
            "Versatility": data.get("versatility", 0),
            "Melee Crit": data.get("melee_crit", {}).get("value", 0),
            "Melee Haste": data.get("melee_haste", {}).get("value", 0),
            "Mastery": data.get("mastery", {}).get("value", 0),
            "Spell Power": data.get("spell_power", 0),
            "Spell Crit": data.get("spell_crit", {}).get("value", 0),
            "Dodge": data.get("dodge", {}).get("value", 0),
            "Parry": data.get("parry", {}).get("value", 0),
            "Block": data.get("block", {}).get("value", 0)
        }
    print(f"Erro ao obter estatísticas do personagem {character_name}: {response.status_code}")
    return {}

def calculate_percentile(df, player_name, realm_slug):
    """Calcula o percentil do jogador em relação ao restante da base de dados com base nos Achievement Points."""
    player_name = player_name.lower()
    realm_slug = realm_slug.lower()

    # Converte a coluna para números inteiros para evitar problemas
    df["Achievement Points"] = pd.to_numeric(df["Achievement Points"], errors="coerce").fillna(0).astype(int)

    player_row = df[(df["Character Name"].str.lower() == player_name) & 
                    (df["Realm Slug"].str.lower() == realm_slug)]

    if player_row.empty:
        print(f"Player {player_name} no realm {realm_slug} não encontrado na base.")
        return None

    player_points = int(player_row["Achievement Points"].values[0])
    percentile = (df["Achievement Points"] < player_points).mean() * 100
    
    print(f"{player_name} está no percentil {percentile:.2f} em relação aos Achievement Points da base.")
    return percentile

def get_google_sheets_df(spreadsheet_id, sheet_name, credentials_file):
    """Lê a planilha do Google Sheets e retorna um DataFrame do pandas."""
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)
    data = sheet.get_all_records()
    
    # Converte para DataFrame e substitui valores vazios por 0
    return pd.DataFrame(data).fillna(0)

def update_google_sheets(df, spreadsheet_id, sheet_name, credentials_file):
    """
    Atualiza ou adiciona registros únicos ao Google Sheets sem sobrescrever a planilha.
    A comparação é feita com base em Character Name + Realm Slug.
    """
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(credentials_file, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)

    # Lê os dados existentes
    existing_data = sheet.get_all_values()
    if not existing_data:
        # Se não houver nada, apenas escreve todos os dados com cabeçalho
        sheet.append_rows([df.columns.tolist()] + df.fillna("").astype(str).values.tolist())
        print(f"✅ Planilha estava vazia. {len(df)} registros adicionados.")
        return

    existing_df = pd.DataFrame(existing_data[1:], columns=existing_data[0])

    # Geração de chaves de comparação
    df["__key__"] = df["Character Name"].str.lower() + "_" + df["Realm Slug"].str.lower()
    existing_df["__key__"] = existing_df["Character Name"].str.lower() + "_" + existing_df["Realm Slug"].str.lower()

    # Verifica novos registros
    novos_registros = df[~df["__key__"].isin(existing_df["__key__"])].drop(columns="__key__")

    # Prepara e envia apenas os novos
    if not novos_registros.empty:
        safe_df = novos_registros.replace([pd.NA, None, float("inf"), float("-inf")], "").fillna("")
        values = safe_df.astype(str).values.tolist()
        sheet.append_rows(values, value_input_option="USER_ENTERED")
        print(f"✅ {len(values)} novos registros adicionados à planilha.")
    else:
        print("ℹ️ Nenhum novo registro para adicionar.")



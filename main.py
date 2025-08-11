from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
import pickle
import os
from dotenv import load_dotenv
import json
from agno.agent import Agent
from agno.tools.tavily import TavilyTools
from agno.models.groq import Groq
from agno.playground import Playground
from agno.storage.sqlite import SqliteStorage
from agno.agent import Agent
import dateparser
from agno.tools.decorator import tool
import multiprocessing
from hypercorn.asyncio import serve
from hypercorn.config import Config
import asyncio
def cria_env():
    if not os.path.exists(".env"):
        print("Arquivo .env não encontrado, vamos criar um agora...")
        groq_key = input("Digite sua GROQ_API_KEY: ").strip()
        client_id = input("Digite seu CLIENT_ID: ").strip()
        client_secret = input("Digite seu CLIENT_SECRET: ").strip()
        tavily_key = input("Digite sua TAVILY_API_KEY: ").strip()

        with open(".env", "w") as f:
            f.write(f"GROQ_API_KEY={groq_key}\n")
            f.write(f'TAVILY_API_KEY={tavily_key}\n')
            f.write(f"CLIENT_ID={client_id}\n")
            f.write(f"CLIENT_SECRET={client_secret}\n")
        print(".env criado com sucesso!")

def carrega_env():
    load_dotenv()
    groq_key = os.getenv("GROQ_API_KEY")
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    tavily_key = os.getenv("TAVILY_API_KEY")
    return groq_key, client_id, client_secret, tavily_key

def cria_credentials_json():
    load_dotenv()
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")

    if not client_id or not client_secret:
        print("Faltando CLIENT_ID ou CLIENT_SECRET no .env")
        return
    
    cred_json = {
      "installed": {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "redirect_uris": [
          "urn:ietf:wg:oauth:2.0:oob",
          "http://localhost"
        ]
      }
    }

    if not os.path.exists("credentials.json"):
        with open("credentials.json", "w") as f:
            json.dump(cred_json, f, indent=2)
        print("Arquivo credentials.json criado com sucesso!")
    else:
        print("Arquivo credentials.json já existe.")

SCOPES = ['https://www.googleapis.com/auth/calendar']

def autenticar_google():
    creds = None
    if os.path.exists('token.pkl'):
        with open('token.pkl', 'rb') as token:
            creds = pickle.load(token)
            
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Token expirado, tentando atualizar...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Não foi possível atualizar o token: {e}")
                print("Por favor, realize a autenticação novamente.")
                creds = None
        
        if not creds:
             flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
             creds = flow.run_local_server(port=0)
        
        with open('token.pkl', 'wb') as token:
            pickle.dump(creds, token)
            
    service = build('calendar', 'v3', credentials=creds)
    return service

GOOGLE_CALENDAR_SERVICE = None
DATE_SETTINGS = {'PREFER_DATES_FROM': 'future', 'DATE_ORDER': 'DMY'}

@tool
def criar_evento(titulo, descricao, data_hora_inicio, data_hora_fim):
    """ 
    Cria um lembrete no Google Calendário com as informações fornecidas.
    Args:
        titulo (str): Título do evento.
        descricao (str): Descrição detalhada do evento.
        data_hora_inicio (str): Data e hora de início no formato legível (ex: '01/10/2023 10:00', com o padrão dia/mês/ano).
        data_hora_fim (str): Data e hora de término no formato legível, igual ao de início.
    Returns:
        str: Mensagem de confirmação da criação, incluindo o ID do evento criado, título e data, ou uma mensagem de erro detalhada.
    """
    try:
        parsed_inicio = dateparser.parse(data_hora_inicio, settings=DATE_SETTINGS)
        parsed_fim = dateparser.parse(data_hora_fim, settings=DATE_SETTINGS)
        if not parsed_inicio or not parsed_fim:
            return f"Erro: Não consegui entender as datas fornecidas. Início: '{data_hora_inicio}', Fim: '{data_hora_fim}'. Use o formato DD/MM/AAAA HH:MM."

        evento = {
            'summary': titulo,
            'description': descricao,
            'start': { 'dateTime': parsed_inicio.isoformat(), 'timeZone': 'America/Sao_Paulo' },
            'end': { 'dateTime': parsed_fim.isoformat(), 'timeZone': 'America/Sao_Paulo' },
        }
        
        evento_criado = GOOGLE_CALENDAR_SERVICE.events().insert(calendarId='primary', body=evento).execute()
        return f"Evento criado com sucesso: '{evento_criado.get('summary')}' (ID: {evento_criado.get('id')})"
    except HttpError as error:
        return f"Ocorreu um erro na API do Google Calendar ao criar o evento: {error}"
    except Exception as e:
        return f"Ocorreu um erro inesperado ao criar o evento: {e}"

@tool
def remover_evento(evento_id):
    """
    Remove um lembrete do Google Calendário.
    Args:
        evento_id (str): ID do evento a ser removido.
    Returns:
        str: Mensagem de confirmação da remoção ou uma mensagem de erro.
    """
    try:
        evento = GOOGLE_CALENDAR_SERVICE.events().get(calendarId='primary', eventId=evento_id).execute()
        GOOGLE_CALENDAR_SERVICE.events().delete(calendarId='primary', eventId=evento_id).execute()
        return f"Evento '{evento.get('summary')}' removido com sucesso." 
    except HttpError as error:
        return f"Ocorreu um erro na API do Google Calendar ao remover o evento. Verifique se o ID '{evento_id}' está correto. Erro: {error}"
    except Exception as e:
        return f"Ocorreu um erro inesperado ao remover o evento: {e}"

@tool
def listar_eventos():
    """
    Lista os próximos 10 eventos do Google Calendário.
    Returns:
        list or str: Lista de eventos futuros ou uma mensagem de erro.
    """
    try:
        eventos_result = GOOGLE_CALENDAR_SERVICE.events().list(
            calendarId='primary', maxResults=10, singleEvents=True, orderBy='startTime'
        ).execute()
        
        items = eventos_result.get('items', [])
        if not items:
            return "Nenhum evento futuro encontrado na sua agenda."

        eventos_listados = []
        for evento in items:
            start = evento['start'].get('dateTime', evento['start'].get('date'))
            end = evento['end'].get('dateTime', evento['end'].get('date'))
            eventos_listados.append({
                'id': evento.get('id'),
                'titulo': evento.get('summary', 'Sem título'),
                'data_hora_inicio': start,
                'data_hora_fim': end
            })
        return eventos_listados
    except HttpError as error:
        return f"Ocorreu um erro na API do Google Calendar ao listar os eventos: {error}"
    except Exception as e:
        return f"Ocorreu um erro inesperado ao listar eventos: {e}"

@tool
def atualizar_evento(evento_id, titulo=None, descricao=None, data_hora_inicio=None, data_hora_fim=None):
    """
    Atualiza um evento existente no Google Calendário.
    Args:
        evento_id (str): ID do evento a ser atualizado.
        titulo (str, optional): Novo título do evento.
        descricao (str, optional): Nova descrição do evento.
        data_hora_inicio (str, optional): Nova data e hora de início no formato DD/MM/AAAA HH:MM.
        data_hora_fim (str, optional): Nova data e hora de término no formato DD/MM/AAAA HH:MM.
    Returns:
        str: Mensagem de confirmação da atualização ou uma mensagem de erro.
    """
    try:
        evento = GOOGLE_CALENDAR_SERVICE.events().get(calendarId='primary', eventId=evento_id).execute()

        if titulo:
            evento['summary'] = titulo
        if descricao:
            evento['description'] = descricao
        if data_hora_inicio:
            evento['start']['dateTime'] = dateparser.parse(data_hora_inicio, settings=DATE_SETTINGS).isoformat()
        if data_hora_fim:
            evento['end']['dateTime'] = dateparser.parse(data_hora_fim, settings=DATE_SETTINGS).isoformat()

        evento_atualizado = GOOGLE_CALENDAR_SERVICE.events().update(calendarId='primary', eventId=evento_id, body=evento).execute()
        return f"Evento atualizado com sucesso: '{evento_atualizado.get('summary')}' (ID: {evento_atualizado.get('id')})"
    except HttpError as error:
        return f"Ocorreu um erro na API do Google Calendar ao atualizar o evento. Verifique se o ID '{evento_id}' está correto. Erro: {error}"
    except Exception as e:
        return f"Ocorreu um erro inesperado ao atualizar o evento: {e}"

print("--- Iniciando Configuração do Assistente ---")
cria_env()
groq_key, client_id, client_secret, tavily_key = carrega_env()
cria_credentials_json()

print("\n--- Autenticando com a API do Google Calendar ---")
try:
    GOOGLE_CALENDAR_SERVICE = autenticar_google()
    print("Autenticação com Google Calendar bem-sucedida!\n")
except Exception as e:
    print(f"ERRO CRÍTICO: Falha na autenticação inicial do Google. O assistente não poderá gerenciar eventos.")
    print(f"Detalhes do erro: {e}")
    exit()

db = SqliteStorage(table_name="agent_session", db_file="tmp/agent.db")

agente = Agent(
    name="Agente do Denis",
    model=Groq(id="deepseek-r1-distill-llama-70b"),
    instructions=['''Você é o assistente pessoal do Denis, um homem que trabalha com SAP Business One. 
Sua tarefa é ajudar a gerenciar eventos no Google Calendar. Você pode criar, remover, listar e atualizar eventos.
Use as ferramentas disponíveis para realizar essas tarefas.
Se o usuário solicitar algo que não esteja relacionado a eventos, informe que você só pode ajudar com eventos no Google Calendar,
e que ele pode listar, criar, remover ou atualizar eventos.
Além disso, você pode buscar informações na internet usando a ferramenta Tavily.
Seja sempre claro e objetivo em suas respostas, e evite informações desnecessárias.
Se Denis solicitar algo relacionado ao Sap Business One, tente buscar informações na internet usando a ferramenta Tavily.
Ao listar eventos, mostre também o ID de cada evento, pois ele é necessário para atualizar ou remover eventos.'''],
    tools=[
        TavilyTools(),
        atualizar_evento,
        criar_evento,
        remover_evento,
        listar_eventos
    ],
    storage=db,
    add_history_to_messages=True,
    num_history_runs=3
)

own_tools_app = Playground(agents=[agente])
app = own_tools_app.get_app()
app.openapi_prefix = "/v1/playground"

def start_server():
    import multiprocessing
    import asyncio
    from hypercorn.config import Config
    from hypercorn.asyncio import serve

    multiprocessing.freeze_support()
    print("--- Servidor do Playground pronto ---")

    playground_url = "https://app.agno.com/playground?endpoint=localhost%3A7777/v1"

    inner_width = len(playground_url) + 2
    top_border = "┏" + "━" * inner_width + "┓"
    bottom_border = "┗" + "━" * inner_width + "┛"
    
    print(top_border)
    print(f"┃ {playground_url} ┃")
    print(bottom_border)

    config = Config()
    config.bind = ["127.0.0.1:7777"]
    config.use_reloader = False

    print('--- Deixe esta janela aberta para deixar o servidor rodando ---')
    print('--- Pressione Ctrl+C ou feche esta janela para desligar o servidor ---')
    print('--- Para acessar o playground, copie o link acima e cole no seu navegador ---')

    asyncio.run(serve(app, config))



if __name__ == "__main__":
    start_server()

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
        # Pega o nome do evento antes de deletar para uma resposta mais amigável
        evento = GOOGLE_CALENDAR_SERVICE.events().get(calendarId='primary', eventId=evento_id).execute()
        titulo_evento = evento.get('summary', 'Sem Título')
        
        GOOGLE_CALENDAR_SERVICE.events().delete(calendarId='primary', eventId=evento_id).execute()
        return f"Evento '{titulo_evento}' removido com sucesso." 
    except HttpError as error:
        if error.resp.status == 404:
            return f"Erro: Evento com ID '{evento_id}' não encontrado. Por favor, verifique o ID e tente novamente."
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
    Atualiza um evento existente no Google Calendário. Apenas os campos fornecidos serão alterados.
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
            parsed_inicio = dateparser.parse(data_hora_inicio, settings=DATE_SETTINGS)
            if not parsed_inicio:
                return f"Erro: Data de início inválida: '{data_hora_inicio}'."
            evento['start']['dateTime'] = parsed_inicio.isoformat()
        if data_hora_fim:
            parsed_fim = dateparser.parse(data_hora_fim, settings=DATE_SETTINGS)
            if not parsed_fim:
                return f"Erro: Data de fim inválida: '{data_hora_fim}'."
            evento['end']['dateTime'] = parsed_fim.isoformat()

        evento_atualizado = GOOGLE_CALENDAR_SERVICE.events().update(calendarId='primary', eventId=evento_id, body=evento).execute()
        return f"Evento atualizado com sucesso: '{evento_atualizado.get('summary')}' (ID: {evento_atualizado.get('id')})"
    except HttpError as error:
        if error.resp.status == 404:
            return f"Erro: Evento com ID '{evento_id}' não encontrado para atualização. Por favor, verifique o ID."
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
    model=Groq(id="llama-3.3-70b-versatile"), 
    instructions=[
        '''Você é um assistente pessoal eficiente para o Denis, especializado em gerenciar a agenda dele no Google Calendar.
        Seu objetivo é executar tarefas de forma precisa usando as ferramentas disponíveis. Seja direto e proativo.

        **Seu Processo Lógico:**

        1.  **Analisar o Pedido:** Entenda claramente a intenção do Denis: criar, listar, remover ou atualizar um evento.

        2.  **Verificar Informações:**
            - Para **criar** um evento, você precisa de: `titulo` e `data_hora_inicio`, pergunte ao Denis se quer adicionar `descricao` e `data_hora_fim`.
            - Para **remover** ou **atualizar**, você precisa do `evento_id`.

        3.  **Lógica para Obter o `evento_id`:**
            - Se o Denis pedir para remover ou atualizar um evento sem fornecer o `evento_id`, sua **primeira e única ação** deve ser usar a ferramenta `listar_eventos`.
            - Apresente a lista de eventos para o Denis de forma clara (com título, data e ID) e pergunte qual deles ele deseja modificar.
            - **Não tente adivinhar.** Aguarde o Denis fornecer o `evento_id` exato.

        4.  **Execução e Confirmação (Pós-Ação):**
            - Uma vez que você tenha **todas** as informações necessárias, use a ferramenta apropriada imediatamente.
            - **Não peça permissão antes de agir** se você já tem os dados (isso evita conversas redundantes que causam duplicatas).
            - Após a execução da ferramenta, informe o resultado ao Denis de forma clara, seja sucesso ou erro. Se for sucesso, inclua o ID do evento modificado ou criado.

        **Regras Cruciais:**
        - **Precisão nos Dados:** Sempre use o formato `DD/MM/AAAA HH:MM` ao se comunicar com o Denis.
        - **Nunca Improvise:** Se não tiver certeza ou faltar informações, sempre pergunte ao Denis.
        - **Foco na Ferramenta:** Priorize o uso das ferramentas. Para conhecimento geral, use o Tavily.
        - **Denis trabalha com SAP Business One:** Se o Denis mencionar SAP, entenda que ele está se referindo ao sistema de gestão empresarial. Se ele pedir algo relacionado a SAP, você deve usar o Tavily para buscar informações relevantes.
        - **Um Passo de Cada Vez:** Execute uma ação de cada vez. Se precisar de um ID, sua única tarefa é listar os eventos e esperar a resposta.
        '''
    ],
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

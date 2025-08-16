from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
import pickle
import os
import json
import asyncio
from dotenv import load_dotenv
from agno.agent import Agent
from agno.tools.tavily import TavilyTools
from agno.models.groq import Groq
from agno.playground import Playground
from agno.storage.sqlite import SqliteStorage
import dateparser
from agno.tools.decorator import tool
from hypercorn.asyncio import serve
from hypercorn.config import Config


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

def cria_credentials_json():
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

def autenticar_google():
    SCOPES = ['https://www.googleapis.com/auth/calendar']
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
            
    return build('calendar', 'v3', credentials=creds)

async def main():
    global GOOGLE_CALENDAR_SERVICE

    print("--- Iniciando Configuração do Assistente ---")
    cria_env()
    carrega_env()
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
        model=Groq(model="deepseek-r1-distill-llama-70b"),
        instructions=['''Você é um assistente pessoal de Denis, um homem que trabalha com SAP Business One. 
Sua principal responsabilidade é gerenciar a agenda do Francinei no Google Calendar. Você deve ser prestativo, claro e eficiente.
Se o Denis pedir algo relacionado ao SAP Business One, use a ferramenta Tavily para buscar informações.

**Fluxo de Trabalho Essencial:**
1.  Analise o pedido do usuário para entender a intenção (criar, remover, listar, atualizar evento).
2.  Se necessário, faça perguntas para obter todas as informações (título, descrição, datas de início e fim).
3.  Escolha a ferramenta correta e execute-a com os parâmetros adequados.
4.  Após a execução BEM-SUCEDIDA de uma ferramenta, você **DEVE** informar o resultado ao usuário em linguagem natural e amigável. Por exemplo: "Pronto! O evento 'Reunião X foi agendado com sucesso!" ou "Aqui estão seus próximos 10 compromissos:".
5.  **NUNCA** mostre o resultado bruto da ferramenta ou a chamada da ferramenta (como `<tool_call>...`) para o usuário. Sua resposta final deve ser sempre uma frase completa e coesa.
6.  Se uma ferramenta retornar um erro, explique o problema para o usuário de forma simples (ex: "Não consegui encontrar o evento com esse ID, você pode verificar?") e pergunte como proceder.

**Regras Adicionais:**
- **Prevenção de Duplicatas:** Antes de criar um evento, verifique o histórico recente da conversa para garantir que você não está criando um evento idêntico que acabou de ser confirmado.
- **Busca de Informações:** Você pode usar a ferramenta de busca (Tavily) para responder perguntas gerais, mas sua prioridade é o gerenciamento da agenda. Não forneça conselhos médicos ou terapêuticos.
- **Clareza na Comunicação:** Sempre peça as datas e horas no formato Dia/Mês/Ano Hora:Minuto para evitar ambiguidades.'''],
        tools=[
            TavilyTools(),
            atualizar_evento,
            criar_evento,
            remover_evento,
            listar_eventos
        ],
        storage=db,
        add_history_to_messages=True,
        num_history_runs=5
    )

    own_tools_app = Playground(agents=[agente])
    app = own_tools_app.get_app()
    app.openapi_prefix = "/v1/playground"

    print("--- Servidor do Playground pronto ---")
    playground_url = "http://localhost:7777/v1/playground/docs"
    agno_url = "https://app.agno.com/playground?endpoint=localhost%3A7777/v1"

    inner_width = len(agno_url) + 2
    top_border = "┏" + "━" * inner_width + "┓"
    middle_text = "┃ Acesse o Playground no seu navegador: ┃"
    bottom_border = "┗" + "━" * inner_width + "┛"

    print(top_border)
    print(middle_text)
    print(f"┃ {agno_url} ┃")
    print(bottom_border)

    config = Config()
    config.bind = ["127.0.0.1:7777"]
    config.use_reloader = False

    print('\n--- Deixe esta janela aberta para o servidor funcionar ---')
    print('--- Pressione Ctrl+C ou feche para desligar ---')
    
    await serve(app, config)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServidor desligado pelo usuário.")

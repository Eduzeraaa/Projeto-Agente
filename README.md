# Projeto-Agente
## Sobre o projeto
Este projeto é um agente inteligente em Python que gerencia eventos no Google Calendar via API. Inicialmente, foi desenvolvido para meus familiares, com o intuito de ajudá-los no dia a dia, otimizando e economizando tempo.
## Funcionalidades
- Criação de eventos com título, descrição, data e horário personalizados;
- Listagem dos próximos eventos futuros para fácil visualização da agenda;
- Atualização de eventos existentes com novos dados;
- Remoção de eventos pelo ID ou descrição.
## Tecnologias Usadas
- Python – Linguagem principal do projeto;
- Google Calendar API – Para manipulação de eventos na agenda;
- google-auth-oauthlib e google-api-python-client – Autenticação e comunicação com API Google;
- Agno – Framework para criação do agente inteligente;
- dateparser – Manipulação flexível de datas e horários.
## Como Usar
- 1 - Baixe o arquivo Agente.exe, e abra-o
- 2 - Na primeira vez que abrir, ele pedirá que você crie algumas API Keys (apenas na primeira vez).
- 3 - Acesse: https://console.groq.com
- 4 - Crie uma conta (ou entre com o Google);
- 5 - Vá até a aba API Keys (canto superior direito);
- 6 - Clique em Create API Key;
- 7 - Escolha um nome pra sua Key, e clique em Submit;
- 8 - Copie ela. ⚠️ Todas as chaves que você criar são de uso único e exclusivo SEU. Não compartilhe suas chaves com ninguém.
- 9 - Insira a API Key como pedido no programa;
- 10  - Acesse o https://console.cloud.google.com
- 11 - Crie um novo projeto.
- 12 - No menu, vá em APIs e Serviços > Biblioteca e ative a Google Calendar API.
- 13 - Vá para APIs e Serviços > Credenciais.
- 14 - Clique em Criar credenciais > ID do cliente OAuth.
- 15 - Escolha o tipo Aplicativo para web.
- 16 - Defina o nome e adicione isso no URIs de redirecionamento autorizados: http://localhost/
- 17 - Faça o download do arquivo JSON das credenciais e guarde ele na pasta do projeto como credentials.json.
- 18 - Insira primeiro a client_id, e depois a client_secret, como pedido no programa.
- 19 - Agora, acesse https://www.tavily.com/
- 20 - Crie uma conta (ou entre com o Google);
- 21 - Copie a sua API Key pré-gerada.
- 22 - Insira a API Key como pedido no programa;
- 23 - Após esses passos, um link será gerado. Copie o link, e cole no seu navegador.
- 24 - Crie uma conta (ou entre com o Google, ou com o GitHub)
- 25 - Em endpoints, na parte na direita, confira se está selecionado a opção localhost:7777/v1
- 26 - Caso não apareça, clique em add endpoint, e cole: http://localhost/7777/v1
- 27 - Ao finalizar, atualize a página, selecione o endpoint recém criado, e pronto!

![agente bot](https://github.com/user-attachments/assets/90a3a4ac-676c-45c5-bc4e-88c211fb35a9)

# Projeto CV: como usar

## Interface atual v3.2.0

Abra http://127.0.0.1:8770/?v=3.2.0#videos. Recarregue com Ctrl+F5 se necessário.

- Adicione arquivos ou links no formulário pequeno no topo. Aguarde terminar o envio e clique em Processar. O programa local faz transcrição e imagens sem participação do assistente.
- Visão geral: Hoje, dia escolhido, mês da data escolhida ou histórico completo. Contagem de vídeos distintos com conclusões registradas no período; inclui alertas e não duplica reprocessamentos da mesma etapa. O total da biblioteca inclui material antigo importado. Não confundir atividade do período com estado atual ou aprovação humana.
- Abaixo, acompanhe o lote atual/último lote. Abra “Ver os vídeos e seus resultados” para os detalhes. A barra fica visível somente enquanto há processamento ativo.
- Biblioteca inteira, por rede/perfil, aparece em “De onde vêm os vídeos”. “Importados do histórico” são registros antigos sem etapas do programa atual; não contam automaticamente como novos sucessos.
- Fila vazia não mostra contagem zero. Se estiver pausada, use Retomar para permitir que futuros lotes em espera comecem automaticamente. Processar um lote com o programa ocioso continua disponível.
- Workflow: linhas contínuas mostram ordem; tracejadas mostram relações de registro e troca de arquivos da IA, sem representar tráfego ao vivo. Concluído se refere à execução técnica, não a uma interpretação pelo chat.

Para seu teste independente: envie os novos vídeos pelo painel, acompanhe as etapas e consulte Falhas e alertas se alguma não terminar. Não peça à IA para preencher transcrições ou estados faltantes. Os arquivos originais, transcrição do programa, imagens e eventos são a evidência do que aconteceu; logs sozinhos não garantem precisão da transcrição.

Relatório desta alteração: relatorios/DESIGN_V320.md. Nenhum vídeo novo foi processado para testar o design.

## Histórico da correção v3.1.1

Abra http://127.0.0.1:8770/?v=3.1.1. Se uma aba antiga continuar com a interface anterior, recarregue com Ctrl+F5. Os arquivos da interface têm versão e as respostas novas não devem ficar em cache. Quando uma versão posterior for detectada, aparece um botão para carregar a atualização.

- Workflow e Vídeos mostram o total inteiro do lote, incluindo vídeos ainda não iniciados. O funil separa entradas enviadas, vídeos aceitos e links recusados. Exemplo histórico: 24 entradas = 21 vídeos + 3 posts de fotos recusados; não são 24 downloads.
- A barra de preparação reaproveita etapas já concluídas e avança conforme a transcrição informa o horário de áudio alcançado. Não é previsão de tempo: fala reconhecida não avança de modo uniforme. 100% preparado não significa interpretado pela IA ou aprovado pelo usuário.
- “Acompanhar atual” volta à execução mais recente. Ao selecionar uma execução antiga, o recorte é identificado como histórico. Banco/biblioteca incluem também os oito vídeos migrados, que não pertencem ao lote dos 21 links.
- Só contam como “prontos para IA” os pacotes com transcrição e imagens correspondentes, arquivos presentes e pré-requisitos técnicos válidos. Pacotes antigos inválidos ficam bloqueados até reprocessamento; o registro antigo continua preservado.
- O aviso da IA pode ser fechado pelo × e permanece oculto neste navegador. Em Vídeos, “Mostrar aviso da IA” reabre. Fechar o aviso não apaga os pacotes.
- A fila ignora vídeos que já estejam no lote ativo ou em outra posição da fila. É possível pausar/retomar e cancelar um lote de espera. Cancelamento não interrompe o lote em execução. O conteúdo e o motivo ficam preservados em dados/fila_historico.jsonl.
- “Falhas e alertas” mostra vídeos com falha aberta. Registros por etapa/checagem e erros históricos são detalhados separadamente; vários registros podem pertencer ao mesmo vídeo. As telas atualizam enquanto abertas.
- Sem pulso recente, o painel informa “sem sinal”, sem alterar o banco para fingir que a execução terminou. Uma leitura do painel nunca promove etapas a concluídas.

Auditoria desta correção: relatorios/auditoria_correcao_painel.json. Um registro marcado “parcial” não significa que o lote terminou. A auditoria final pode ser repetida pelo programa: `.venv\Scripts\python.exe -m app.auditar_estado --final`.

## Abrir o painel
Dê dois cliques em **`ABRIR_PAINEL.bat`**. O navegador abre em http://127.0.0.1:8770.
O painel roda só no seu PC. Para desligar, feche a janela preta.

## Processar vídeos
Há dois jeitos:
- **Pelo painel:** aba **Vídeos** → arraste os arquivos (ou cole os links) → **Processar**.
  Acompanhe na própria aba (barras de progresso) ou no **Workflow** (ao vivo).
- **Pelo terminal** (PowerShell, dentro de `S:\CV`):
  ```
  .venv\Scripts\python.exe -m app.pipeline --links listas\victhor_cv.txt --limite 1
  ```
  A execução aparece no painel do mesmo jeito.

Opções úteis:
- `--ia claude` ou `--ia openai` (precisa da chave);
- `--modelo <nome>`;
- `--reprocessar` (refaz tudo);
- `--refazer-ia` (refaz só a interpretação).

## Etapa de IA (sem chave paga)
1. O programa deixa um **pacote** por vídeo (`ia/PARA_IA.md`) e lista todos em `dados/PENDENTES_IA.md`.
2. O painel mostra a faixa roxa "aguardando a IA".
3. No chat (Claude no app, com a pasta S:\CV conectada, ou ChatGPT/Codex com acesso à pasta), peça:
   **"Interprete os vídeos pendentes em S:\CV"**.
4. A IA grava `ia/resposta_chat.json`. O painel **importa e confere sozinho** em poucos segundos:
   - citações existem na transcrição?
   - todas as imagens foram descritas?
   - as imagens citadas existem?

Opcional: com chaves de API no `.env` (veja `.env.exemplo`), dá para usar `--ia claude` ou `--ia openai` direto pelo terminal. É pago.

## Onde fica cada coisa
| Pasta | Conteúdo |
|---|---|
| `app/` | código (pipeline, servidor, painel) |
| `dados/cv.db` | **banco único** |
| `dados/videos/<perfil>/<id>/` | vídeo, `transcricao.json`, `frames/`, `ia/` (pedido e resposta exatos), `RESUMO.md` |
| `logs/eventos.jsonl` | todos os eventos de todas as execuções (nada é apagado) |
| `listas/` | listas de links para processar |
| `relatorios/`, `curriculos/` | saídas das próximas fases |
| `arquivo/` | fase anterior (ChatGPT/Codex), guardada intacta, com `MOVIMENTACOES.csv` |

## Etapas e quem faz cada uma
1. **Baixar** (programa): yt-dlp. Confere tamanho, áudio e duração.
2. **Transcrever** (programa): Whisper, no seu PC.
3. **Extrair imagens** (programa): 1 a cada 1,5 s. Guarda só as diferentes e registra quais foram descartadas por serem repetidas.
4. **Checar integridade** (programa):
   - a transcrição vai até o fim do vídeo?
   - há lacunas sem fala?
   - número de imagens = duração ÷ intervalo?
   - os arquivos existem?
5. **Interpretar com IA** (IA do chat): o pacote tem a transcrição inteira e até 30 imagens. Ao importar a resposta, o programa confere:
   - quanto foi enviado;
   - se cada citação existe literalmente na transcrição;
   - se todas as imagens foram descritas;
   - se as imagens citadas estavam mesmo no pacote.
6. **Relatório** (programa): gera o `RESUMO.md` do vídeo.

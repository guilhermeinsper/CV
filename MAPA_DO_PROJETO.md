# MAPA DO PROJETO CV: leia isto primeiro
Atualizado em 16/10/2026 durante a correção pelo Codex. Toda IA que trabalhar aqui deve seguir o `AGENTS.md` e atualizar este arquivo ao terminar. O estado vigente abaixo substitui o histórico de 19h05.

## Estado vigente: design v3.2.0 (16/10/2026)

Esta atualização substitui a interface v3.1.1 descrita no histórico abaixo. Abrir http://127.0.0.1:8770/?v=3.2.0#videos e recarregar a aba para carregar o JavaScript novo.

- Pedido atual: ajustar design antes de o usuário testar novos vídeos sozinho. NÃO interpretar pendentes, produzir transcrições manualmente nem processar seus próximos arquivos nesta etapa.
- Vídeos: envio compacto no topo; visão geral com Hoje, dia, mês e histórico completo; último lote separado; lista detalhada recolhível; totais por rede/perfil. Datas sem relógio nos resumos. Horários de auditoria preservados nos logs/detalhes.
- app/resumo.py conta vídeos distintos por etapa com evento de conclusão (ok/alerta) no período em São Paulo. Usa o histórico de eventos, não soma reprocessamentos do mesmo vídeo/etapa. O resumo NÃO é o estado atual, nem validação semântica/humana. Biblioteca inclui oito importados do histórico, sem inventar etapas para eles.
- Workflow: status Ativo / Concluído · inativo / Sem operação; progresso só enquanto vivo. Relações das etapas com banco e troca de arquivos da IA voltaram como linhas tracejadas estáticas, identificadas; não simulam tráfego nem interpretação concluída.
- Aviso de fila vazia removido. A fila estava pausada e continuou assim; quando vazia aparece apenas controle discreto para retomar. Novos lotes em espera só avançam automaticamente se a fila estiver retomada.
- Envio agora usa nome único para impedir sobrescrita de arquivos homônimos no mesmo segundo. Processar fica bloqueado durante upload e ignora duplo clique; arquivos enviados permanecem ao voltar à aba.
- Testado: 18 testes automatizados isolados; navegação nas cinco abas sem erro JavaScript observado; filtros de dia/mês, resumo vazio, permanência de rascunho e detalhes abertos, interface 1440px/390px; estado ativo e upload/duplo clique simulados no navegador, com requisições interceptadas sem tocar vídeos reais. Detalhes em relatorios/DESIGN_V320.md e logs/testes_design_v320.txt.
- NÃO testado nesta etapa: novo vídeo real de ponta a ponta, qualidade semântica das transcrições, nova resposta real de IA, redes além das já suportadas. Pipeline/Whisper não foram alterados; não houve novo processamento nem interpretação.
- Backup anterior: arquivo/design_painel_2026-10-16_v320. Relatório estruturado: relatorios/design_v320.json. Tokens e custos deste chat não mensurados (null); não declarar zero consumo do assistente.

## Histórico: correção do painel v3.1.1

**FECHAMENTO CONFERIDO em 16/10/2026, 19h33:** 21 de 21 vídeos preparados, 831 trechos de fala, 1.687 amostras de imagem (1.673 únicas presentes), 21 pacotes válidos, zero pacotes inválidos, zero falhas/alertas técnicos abertos, zero lotes em espera e nenhum processamento ativo. Auditoria final aprovada em relatorios/auditoria_correcao_painel.json; relatório em relatorios/CORRECAO_PAINEL.md. Os 21 aguardam interpretação real da IA, que NÃO foi feita nesta correção. Não confundir esse estado válido com os 21 pacotes inválidos que existiam antes.

O usuário pediu corrigir contadores contraditórios, fila duplicada, aviso não dispensável, falta de progresso e falhas de transcrição. A aplicação atual é app/ na porta 8770; não editar a duplicata painel/ da fase antiga.

- Use http://127.0.0.1:8770/?v=3.1.1 para carregar a interface corrigida. Playwright MCP foi usado para conferir a aplicação; a aba pessoal do Chrome não estava disponível pelo conector.
- A correção de áudio via ffmpeg da v3 já está funcionando no Windows: o lote de 21 iniciado às 19h01 continuou no mesmo processo. O Codex reiniciou somente a interface para carregar correções, sem reiniciar a transcrição.
- Três pedidos idênticos da fila foram arquivados, preservando o conteúdo. Fila agora é deduplicada por ID de vídeo, protegida contra cliques simultâneos e permite pausa/cancelamento. Arquivo fila_historico.jsonl conserva alterações.
- app/estado.py centraliza projeção, validade de pacotes e prontidão. Pré-requisitos, transcrição completa correspondente e imagens existentes/registradas são conferidos. Pacotes inválidos da v2 não contam mais como prontos.
- Workflow/funil usam todos os vídeos aceitos, inclusive não iniciados. Recusas (fotos) ficam separadas. A barra mostra preparação e posição no áudio; interpretação é uma etapa independente. Linhas decorativas para banco/IA foram removidas; linhas restantes mostram ordem, não transferência de dados.
- Falhas contadas por vídeos distintos; detalhes por etapa e histórico permanecem. Execuções, fontes e vídeos usam a mesma projeção de prontidão. Leituras não escrevem status de etapas/execuções; falta de pulso é sinalizada, sem simular conclusão.
- Onze testes de regressão aprovados em banco temporário. QA real confirmou fechamento persistente do aviso, progresso, históricos, pausa/retomada e rejeição de reenvio duplicado. Nenhum vídeo interpretado ou validado pelo Codex nesta correção.
- O teste de queda/recuperação revelou que display:flex impedia esconder o aviso após a conexão voltar. Corrigido com regra de hidden e teste repetido aprovado. A linha contínua entre os blocos era também overflow dos 21 mini-indicadores por nó; largura limitada e contenção medida no navegador.
- Telemetria local de tokens encontrada era anterior a este pedido. relatorios/tokens_correcao_snapshot.json marca explicitamente que não é aplicável. Consumo desta correção permanece não mensurado, não zero.
- Backup antes das alterações: arquivo/correcao_painel_2026-10-16_1908. Evidência visual em relatorios/painel_corrigido_em_execucao.png.
- O fechamento atualizado deve ser consultado em relatorios/auditoria_correcao_painel.json. Enquanto tipo=parcial ou vivo=true, a recuperação dos 21 ainda não terminou. Não alegar conclusão com base apenas nos testes de interface.

## Histórico anterior à correção (19h05, Claude)

---

## 0. ATUALIZAÇÃO VIGENTE: v3.3 (16/10/2026, às 20h20, Claude)
- **Papéis:** Claude é o dono do código. O ChatGPT revisa (em `revisoes/`), interpreta os vídeos e organiza `conteudo/` (ver o topo do `AGENTS.md`).
- **Motor único de números:** `app/metricas.py`. Todas as páginas (Workflow, Vídeos, Execuções, Falhas, rodapé) leem dele, com três recortes rotulados: **Agora** (biblioteca), **Lote** e **Histórico**. O vocabulário de situação é um só: concluído, alerta, falha, aguardando IA, bloqueado, rodando, sem sinal, incompleto, na fila, migrado.
- **Autoconferência:** `metricas.conferir()` roda 9 checagens (ex.: soma das fontes = biblioteca; IA prontos = etapa aguardando; aceitos + recusados = entradas). O resultado aparece no rodapé e no bloco Agora (✓ ou ✗).
- **Saúde:** ao abrir, o painel acha o ffmpeg e o ffprobe e grava a pasta em `config.json` (`ffmpeg_dir`), para os processos filhos herdarem. Confere também o yt-dlp e o modelo Whisper. Corrige o "ffprobe não encontrado" do lote das 20h01.
- **Vídeo registrado na entrada** (antes do download). Os 4 vídeos órfãos do lote das 20h01 são reparados ao abrir o painel.
- **Falhas:** separadas em causa raiz × consequências.
- O código do ChatGPT das 19h09 às 19h53 foi **mantido** (estado.py, fila.py, resumo.py, auditar_estado.py). A v3.3 foi feita por cima dele. Cópia do antes: `arquivo/instalacoes/codigo_chatgpt_2026-10-16_20h06.zip`.
- **Testado na nuvem:** cópia do banco real (9 de 9 checagens ok), ciclo completo (download falho registrado → pacote → resposta → importação) e capturas das 4 páginas sem erro de JS. **Não testado no Windows ainda.**

## 1. Objetivo do usuário
- Estudante de Economia (Insper). Vai se candidatar a **estágios em DCM e Equity Research**. Já tem **3 vagas** separadas, que **ainda não foram enviadas** a nenhuma IA.
- Para montar o CV, quer extrair dicas de vídeos de carreira (TikTok): **o que o autor fala** e **os CVs mostrados na tela**. Tudo vai para um banco de dados auditável.
- Depois (fase 2): um chat (Claude ou GPT) que gere o CV usando **só** as dicas validadas e os dados reais dele.
- Horizonte: usar o sistema **pelo próximo ano**. Tem que ser organizado, durável e honesto.

### Como ele quer trabalhar (regras dele)
- Primeiro **1 vídeo 100% certo**, depois aumentar aos poucos, depois rodar em massa e depois outros perfis.
- **Transparência total:**
  - separar sempre "testado e funciona", "testado e falhou" e "não testado";
  - nunca dizer "revisei" ou "li tudo" sem prova;
  - ele já se sentiu enganado pelo ChatGPT antes.
- **Sem API paga:** a interpretação é feita pela IA do chat (Claude ou ChatGPT no app), via arquivos.
- Ele não quer ver vídeos um por um nem códigos de ID. Quer **números agregados**: por rede social e perfil, quantos vídeos, status, e um funil do que foi baixado, transcrito etc.
- Rodar manualmente está ok. Agendamento automático não é necessário.

---

## 2. Ambiente
- Windows, pasta **S:\CV**. Python 3.14.3 em **`S:\CV\.venv`**.
- Pacotes: yt-dlp com curl-cffi, faster-whisper 1.2.1 (modelo `small` já baixado), pillow, numpy. O ffmpeg 9.0.2 foi instalado via winget.
- **Atenção:**
  - a versão do **PyAV** instalada é incompatível com o faster-whisper 1.2.1 (erro `metadata_errors`). Por isso a v3 extrai o áudio pelo **ffmpeg** (`carregar_audio` em `app/pipeline.py`), e não pelo PyAV;
  - SQLite pela ponte remota (ambiente Linux da IA acessando S:) **trava**. Escrever no banco só pelo Python do Windows, ou trabalhar numa cópia.
- Download do TikTok: `--impersonate chrome --no-check-formats -S vcodec:h264,res:1080`. Sem `--no-check-formats` ele trava. Testado no Windows: funciona (21 de 21 baixados).

## 3. Estrutura da pasta
| Caminho | Conteúdo |
|---|---|
| `app/` | código: `pipeline.py` (6 etapas), `servidor.py` (painel), `importar_ia.py`, `ia.py`, `db.py`, `registro.py`, `migrar.py`, `web/` (interface) |
| `dados/cv.db` | **banco único** (SQLite) |
| `dados/videos/<perfil>/<id>/` | `video.mp4`, `transcricao.json`, `frames/`, `ia/` (`PARA_IA.md`, `pedido_chat.json`, `resposta_chat.json`), `RESUMO.md` |
| `dados/PENDENTES_IA.md` | lista de pacotes esperando a IA |
| `dados/entrada/` | vídeos enviados pelo painel |
| `dados/fila_espera.json` | lotes esperando o processamento atual terminar |
| `logs/eventos.jsonl` | todos os eventos (nada é apagado) |
| `listas/` | listas de links |
| `arquivo/fase1_chatgpt_2026-10-16/` | tudo da fase anterior, intacto (`MOVIMENTACOES.csv`) |
| `arquivo/instalacoes/` | pacotes de instalação v2 e v3 |
| `painel/` (raiz) | **duplicata** do painel antigo. O sistema não deixou apagar; pode ser apagada à mão |
| `ABRIR_PAINEL.bat` | abre o painel em http://127.0.0.1:8770 |

## 4. Como o sistema funciona
**Etapas por vídeo:**
1. **baixar** (programa)
2. **transcrever** (programa: Whisper local)
3. **imagens** (programa: 1 a cada 1,5 s, repetidas descartadas e registradas)
4. **integridade** (programa: transcrição até o fim, lacunas, nº de imagens, arquivos)
5. **interpretar** (IA do chat)
6. **relatório** (programa: `RESUMO.md`)

**Regras de honestidade embutidas no código:**
- Só o programa grava status. Toda etapa gera eventos e checagens.
- Etapa "mantida" preserva o status original (um alerta antigo não vira ok).
- Se a transcrição falha, a IA **não** é preparada (status `pulada`). Uma falha não se repete como várias falhas de consequência.
- A IA do chat responde num arquivo. O programa importa e confere:
  - se cada citação existe literalmente na transcrição;
  - se **todas** as imagens do pacote foram descritas;
  - se as imagens citadas estavam no pacote.
- Pacote velho (feito com outra transcrição) é refeito automaticamente.
- Se o processamento não inicia, o painel mostra o erro (não diz "ok" em silêncio).

**Protocolo da IA do chat** (detalhes no `AGENTS.md`): ler `dados/PENDENTES_IA.md` → para cada vídeo, abrir `PARA_IA.md`, todas as imagens e a transcrição → gravar só `ia/resposta_chat.json` (com `modelo_declarado` e `descricoes_imagens` de todas as imagens) → o painel importa sozinho a cada 5 s.

**Painel (v3)**, com menu lateral:
- **Workflow:** estilo n8n; arrastar com o mouse, zoom com a roda; progresso agregado por etapa; ao vivo.
- **Vídeos:**
  - funil do último lote e da biblioteca;
  - envio por arrastar arquivos ou colar links;
  - fila de espera;
  - barras de progresso por vídeo;
  - tabela "De onde vêm os vídeos" (rede, perfil, quantidade, status, com dicas de mouse);
  - botão "↻ Reprocessar vídeos com falha".
- **Execuções e logs:** indicadores e gráficos.
- **Falhas e alertas:** resumo por causa no topo.
- **Banco de dados.**

O usuário pediu para tirar as abas Rodar, Chat do CV e Como ler este painel.

---

## 5. Histórico (16/10/2026)
1. **Teste no Chrome:** perfil @victhor.jordao listado (pelo menos 491 vídeos; 14 de CV/LinkedIn pela descrição, em `listas/victhor_cv.txt`). O CV na tela é legível por print. Os vídeos não têm legenda, e a IA não ouve o áudio pelo navegador.
2. **Instalação no Windows:** Python, ffmpeg, venv, Whisper. Download destravado com `--no-check-formats`.
3. **Fase ChatGPT/Codex:** o ChatGPT criou muitos scripts, um painel com "cara de página de vendas", 1 vídeo-teste do Victhor (34 falas, 12 recomendações) e 7 vídeos sobre IA baixados à mão. Tudo foi para `arquivo/`.
4. **Reorganização (Claude):** código novo em `app/` e banco único. **Migração conferida:** todas as contagens batem; 820 de 820 imagens encontradas. Os 8 vídeos migrados aparecem como "migrado" (sem etapas registradas).
5. **Painel v1 → v2 → v3** (ajustes pedidos pelo usuário e correções de defeitos encontrados em teste).
6. **Primeiro lote real (painel, 18h48):** 24 links da busca "CV for finance" no TikTok.
   - **3 recusados** (posts de fotos `/photo/`, não suportados).
   - **21 baixados** ✅ e **21 com imagens** ✅.
   - **Transcrição falhou nos 21** ❌ (erro do PyAV `metadata_errors`).
   - Por um defeito já corrigido, a v2 criou pacotes de IA mesmo sem transcrição. Esses 21 pacotes em `PENDENTES_IA.md` são **inválidos** e serão refeitos no reprocessamento.
7. **v3 instalada às 19h00:**
   - correção da transcrição (áudio pelo ffmpeg);
   - IA não preparada se a transcrição falhar;
   - fila de espera;
   - funil;
   - falhas por causa;
   - botão de reprocessar;
   - ordenação de execuções corrigida (havia fusos misturados).

## 6. Estado histórico às 19h05 (substituído pelo fechamento acima)
- **Banco:** 29 vídeos (21 do lote + 8 migrados).
- **Testado na nuvem** (vídeos sintéticos, transcrição e IA simuladas): pipeline, fila de espera, bloqueio da IA sem transcrição, importação da resposta do chat (pegou citação inventada e imagem sem descrição), migração e painel por captura de tela.
- **Testado no Windows:** download (21 de 21) e extração de imagens (21 de 21).
- **NÃO testado no Windows:**
  - transcrição com a correção da v3;
  - painel v3 (precisa reiniciar);
  - importação de uma resposta real da IA do chat.

## 7. Plano histórico às 19h05 (a recuperação técnica já foi concluída)
1. Usuário: **fechar a janela preta do painel e abrir de novo o `ABRIR_PAINEL.bat`** (carrega a v3).
2. Aba Vídeos → **"↻ Reprocessar vídeos com falha"**. Conferir no funil se "Transcritos" chega a 21. Se falhar, a causa aparece em Falhas e alertas.
3. **Não interpretar** antes de o passo 2 dar certo (os pacotes atuais são inválidos).
4. Depois: pedir no chat "interprete os vídeos pendentes em S:\CV". Começar por **1 vídeo** e validar com o usuário.
5. Escalar: 3 vídeos, depois todos. Avaliar o suporte a posts de fotos (carrossel).
6. Fase 2: cadastrar os dados reais do usuário e as 3 vagas, e montar o chat do CV.

## 7b. Próxima fase proposta
- Ver **`PLANO_FIM_DE_SEMANA.md`**: sexta = dentro da porteira 100%; sábado = descoberta; domingo = CV. Inclui o caminho conhecimento → CV.
- Atualização às 20h: **transcrição corrigida e funcionando** (21 de 21; integridade 21 de 21 ok). 21 pacotes válidos aguardando a IA.
- Ver **`PLANO_FORA_DA_PORTEIRA.md`** (descoberta de vídeos em várias plataformas, rodadas noturnas, Claude × ChatGPT). Status: **proposta, não aprovada**.

## 8. Pendências conhecidas
- Posts de fotos do TikTok não são suportados.
- Listagem automática dos vídeos de um perfil: não existe (os links são colados à mão).
- Pasta `painel/` duplicada na raiz e `arquivo/_restos_tentativa_migracao/`: podem ser apagadas à mão.
- `.mcp.json` (Playwright MCP da fase ChatGPT) está em `arquivo/`: apontava para pastas que mudaram.

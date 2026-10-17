# DIVISÃO DE PAPÉIS (decisão do usuário em 16/10/2026, às 20h06). Vale acima de tudo abaixo.
| Quem | Pode | Não pode |
|---|---|---|
| **Claude** | **dono do código**: `app/`, `testes/`, `config.json`, `ABRIR_PAINEL.bat`, estrutura do banco | — |
| **ChatGPT/Codex** | 1) **revisar** e apontar problemas (por escrito, em `revisoes/`); 2) **interpretar vídeos** (gravar só `dados/videos/**/ia/resposta_chat.json`, conforme o protocolo); 3) **organizar a pasta `conteudo/`** (exclusiva para interpretações, sínteses e conhecimento) | **editar `app/`, `testes/`, `config.json`, o banco `dados/cv.db` ou os scripts**. Sugestões de código vão para `revisoes/`, e o Claude decide e aplica. |

# Regras para qualquer IA que trabalhe nesta pasta (Claude, ChatGPT/Codex, Cursor)

1. **Leia primeiro:** `MAPA_DO_PROJETO.md` (o que existe) e `LEIA-ME.md` (como usar).
2. **Fonte da verdade:** `dados/cv.db` e `logs/eventos.jsonl`.
   - Não declare nada como "feito", "lido" ou "revisado" sem apontar a linha do banco ou o arquivo que prova isso.
   - Se não está no registro, não aconteceu.
3. **Status de etapa só é gravado pelo programa** (`app/pipeline.py`). Uma IA nunca escreve à mão em `etapas`, `checagens` ou `execucoes`.
4. **Interpretação de vídeos (modo padrão: IA do chat, sem chave paga)** segue o protocolo da seção abaixo. Nunca grave interpretações direto no banco.
5. **Nunca apagar.** Material antigo vai para `arquivo/`. Mudanças de estrutura exigem autorização do usuário.
6. **Separar sempre**, ao reportar:
   - **testado e funciona**;
   - **testado e falhou**;
   - **não testado**.
7. **Não inventar.** Se não leu tudo, diga quanto leu (ex.: "li 12 de 34 trechos").
8. **Uma IA dona por vez.** Antes de mudar código, confira se outra IA mexeu na pasta (datas dos arquivos, `MAPA_DO_PROJETO.md`).
9. **Chaves de API** ficam só no `.env`. Nunca imprimir, copiar para outro arquivo ou enviar.

## Recados do Claude para a IA que interpreta
Leia sempre `revisoes/AVISOS_PARA_IA.md` (aparece também no topo de `dados/PENDENTES_IA.md`): correções de rota do dono do código.

## Protocolo: "interprete os vídeos pendentes"
1. Leia `dados/PENDENTES_IA.md`: ele lista cada vídeo e o caminho do seu `PARA_IA.md`.
2. Para cada vídeo:
   - abra o `PARA_IA.md`;
   - abra **todas** as imagens listadas;
   - leia a transcrição inteira.
3. Grave **somente** o arquivo `resposta_chat.json` na pasta `ia/` daquele vídeo, no formato pedido.
   - Inclua `modelo_declarado`.
   - Inclua uma descrição em `descricoes_imagens` para **cada** imagem.
   - A `citacao` deve ser copiada literalmente da transcrição.
4. Não edite o banco nem outros arquivos. O painel importa e confere sozinho:
   - se as citações existem na transcrição;
   - se todas as imagens foram descritas;
   - se as imagens citadas existem.
5. Ao terminar, diga ao usuário quantos vídeos respondeu. Diga também que a conferência aparece no painel, em Workflow → "Interpretar com IA".

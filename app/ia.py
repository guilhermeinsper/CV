"""Chamada à IA pela API (Claude ou GPT).

O programa monta o pedido, guarda uma cópia exata do que foi enviado (sem as imagens em
base64, só a lista delas) e a resposta bruta. Por isso a cobertura é MEDIDA, não declarada.
"""
import base64, io, json, re, time, urllib.error, urllib.request
from . import config as C

INSTRUCOES = """Você analisa um vídeo curto de dicas de currículo (mercado financeiro/corporativo).
Você recebe: (1) a TRANSCRIÇÃO AUTOMÁTICA completa, com horários; (2) IMAGENS do vídeo, cada uma
identificada por "Imagem n=<número> (t=<segundos>s)".

Regras obrigatórias:
- Use SOMENTE o que está na transcrição e nas imagens. Não complete com conhecimento próprio.
- "citacao" deve ser um trecho COPIADO LITERALMENTE da transcrição (até 25 palavras). O programa
  confere isso; citação que não existir será marcada como não verificada.
- "inicio_s"/"fim_s" devem vir dos horários da transcrição.
- "frame_n" só pode ser um número de imagem que você recebeu.
- Se um texto na imagem estiver cortado ou ilegível, diga isso em "legibilidade"; não invente.
- A transcrição é automática e pode ter erros; aponte trechos duvidosos em "trechos_duvidosos".

Responda APENAS com um JSON neste formato:
{
 "resumo": "2-3 frases sobre o vídeo",
 "frames_com_cv": [n, ...],
 "cv_exemplos": [{"frame_n": n, "secao": "Cabeçalho|Educação|Experiência|Liderança/Extracurricular|Habilidades|Outro",
                  "texto_lido": "...", "legibilidade": "legivel|parcial|ilegivel"}],
 "recomendacoes": [{"inicio_s": 0.0, "fim_s": 0.0, "categoria": "formato|estrutura|educacao|experiencia|bullets|habilidades|certificacoes|extracurricular|amostra|ats|linkedin|processo_seletivo|outro",
                    "tipo": "fazer|evitar|exemplo", "recomendacao": "...", "citacao": "...",
                    "aplica_a": "geral|IB|DCM|research|corporativo", "frame_n": null, "confianca": "alta|media|baixa"}],
 "trechos_duvidosos": [{"inicio_s": 0.0, "fim_s": 0.0, "texto": "...", "motivo": "..."}]
}"""


class ErroIA(Exception):
    pass


def _img_b64(caminho, lado):
    from PIL import Image
    im = Image.open(caminho).convert("RGB")
    im.thumbnail((lado, lado))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _post(url, cabecalhos, corpo, timeout):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), method="POST",
                                 headers={"content-type": "application/json", **cabecalhos})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise ErroIA(f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")
    except Exception as e:
        raise ErroIA(f"falha de rede/tempo: {e}")


def chamar(provedor, modelo, texto_transcricao, imagens, chave, cfg):
    """imagens: lista de (n, t_s, caminho). Devolve (texto_resposta, uso, pedido_registrado)."""
    lado, timeout = cfg["lado_maior_imagem_ia"], cfg["timeout_ia_s"]
    pedido_registrado = {"provedor": provedor, "modelo": modelo, "instrucoes": INSTRUCOES,
                         "transcricao_enviada": texto_transcricao,
                         "imagens_enviadas": [{"n": n, "t_s": t, "arquivo": C.rel(p)} for n, t, p in imagens]}
    t0 = time.time()
    if provedor == "claude":
        conteudo = []
        for n, t, p in imagens:
            conteudo.append({"type": "text", "text": f"Imagem n={n} (t={t:.1f}s)"})
            conteudo.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                         "data": _img_b64(p, lado)}})
        conteudo.append({"type": "text", "text": "TRANSCRIÇÃO:\n" + texto_transcricao})
        r = _post("https://api.anthropic.com/v1/messages",
                  {"x-api-key": chave, "anthropic-version": "2023-06-01"},
                  {"model": modelo, "max_tokens": 8000, "system": INSTRUCOES,
                   "messages": [{"role": "user", "content": conteudo}]}, timeout)
        texto = "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
        u = r.get("usage", {})
        uso = {"entrada": u.get("input_tokens"), "saida": u.get("output_tokens")}
    elif provedor == "openai":
        conteudo = []
        for n, t, p in imagens:
            conteudo.append({"type": "text", "text": f"Imagem n={n} (t={t:.1f}s)"})
            conteudo.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + _img_b64(p, lado)}})
        conteudo.append({"type": "text", "text": "TRANSCRIÇÃO:\n" + texto_transcricao})
        r = _post("https://api.openai.com/v1/chat/completions", {"authorization": f"Bearer {chave}"},
                  {"model": modelo, "max_completion_tokens": 8000,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": INSTRUCOES},
                                {"role": "user", "content": conteudo}]}, timeout)
        texto = r["choices"][0]["message"].get("content") or ""
        u = r.get("usage", {})
        uso = {"entrada": u.get("prompt_tokens"), "saida": u.get("completion_tokens")}
    else:
        raise ErroIA(f"provedor desconhecido: {provedor}")
    uso["duracao_s"] = round(time.time() - t0, 1)
    return texto, uso, pedido_registrado, r


def extrair_json(texto):
    try:
        return json.loads(texto)
    except Exception:
        m = re.search(r"\{.*\}", texto, re.S)
        if not m:
            raise ErroIA("a resposta da IA não contém JSON")
        try:
            return json.loads(m.group(0))
        except Exception as e:
            try:  # tolera vírgula sobrando antes de } ou ] (erro comum das IAs); o conteúdo continua sendo conferido
                return json.loads(re.sub(r",(\s*[}\]])", r"\1", m.group(0)))
            except Exception:
                raise ErroIA(f"JSON inválido na resposta da IA: {e}")


def normalizar(s):
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

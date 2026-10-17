// Painel de Controle do projeto CV (v2). Só mostra o que está no banco e nos registros.
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = s => { s = Math.round(+s || 0); return `${String(Math.floor(s/60)).padStart(2,"0")}:${String(s%60).padStart(2,"0")}`; };
const dur = s => s == null ? "—" : s < 60 ? `${Math.round(s)} s` : s < 3600 ? `${Math.floor(s/60)} min ${Math.round(s%60)} s` : `${(s/3600).toFixed(1)} h`;
const hora = ts => ts ? new Date(ts).toLocaleTimeString('pt-BR',{timeZone:'America/Sao_Paulo'}) : "";
const dataCurta = ts => ts ? new Date(ts).toLocaleDateString('pt-BR',{timeZone:'America/Sao_Paulo'}) : '—';
const estadoOperacao = d => d.vivo ? 'Ativo' : d.execucao?.status === 'concluida' ? 'Concluído · inativo' : 'Sem operação';
const dataHora = ts => ts ? new Date(ts).toLocaleString('pt-BR',{timeZone:'America/Sao_Paulo'}) : "—";
const api = async (u, corpo) => {try{const r=await fetch(u, corpo ? {method:"POST", headers:{"content-type":"application/json"}, body:JSON.stringify(corpo)} : {cache:'no-store'});const d=await r.json();if(!r.ok)throw Error(d.erro||`HTTP ${r.status}`);const err=document.querySelector('#erro-atualizacao');if(err)err.hidden=true;if(d.versao&&d.versao!==BUILD){let banner=document.querySelector('#atualizacao-painel');if(!banner){banner=document.createElement('div');banner.id='atualizacao-painel';banner.className='faixa-ia';document.body.prepend(banner);}banner.innerHTML='Existe uma versão nova do painel. <button onclick="location.reload()">Carregar atualização</button>'; }return d;}catch(e){let err=document.querySelector('#erro-atualizacao');if(!err){err=document.createElement('div');err.id='erro-atualizacao';err.className='faixa-ia';document.body.prepend(err);}err.textContent='Falha ao atualizar: '+e.message+'. Os números exibidos podem estar antigos.';err.hidden=false;throw e;}};
const midia = p => `/midia?p=${encodeURIComponent(p)}`;

const ETAPAS = [
  {id:"baixar", nome:"Baixar vídeo", quem:"prog", icone:"down", explica:"O programa baixa o vídeo (ou copia o arquivo enviado) e confere tamanho, áudio e duração."},
  {id:"transcrever", nome:"Transcrever áudio", quem:"prog", icone:"onda", explica:"O Whisper, rodando no seu PC, transforma a fala em texto com horários."},
  {id:"imagens", nome:"Extrair imagens", quem:"prog", icone:"img", explica:"Uma imagem a cada 1,5 s; as repetidas são descartadas e registradas."},
  {id:"integridade", nome:"Checar integridade", quem:"prog", icone:"escudo", explica:"Confere se nada se perdeu: transcrição até o fim, lacunas, nº de imagens, arquivos."},
  {id:"interpretar", nome:"Interpretar com IA", quem:"ia", icone:"brilho", explica:"O programa monta um pacote; a IA do chat (Claude ou ChatGPT) responde; o programa importa e confere citações e imagens."},
  {id:"relatorio", nome:"Relatório", quem:"prog", icone:"doc", explica:"Gera o RESUMO.md do vídeo com etapas, checagens e resultados."},
];
const NOME = Object.fromEntries(ETAPAS.map(e => [e.id, e.nome]));
const ICONES = {
  entrada:'<path d="M4 7h16M4 12h16M4 17h10" stroke="#8fa3b8" stroke-width="2.2" stroke-linecap="round"/>',
  down:'<path d="M12 4v11m0 0-4-4m4 4 4-4M5 19h14" stroke="#3ecf8e" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  onda:'<path d="M3 12h2m3-5v10m4-13v16m4-12v8m4-5v2" stroke="#4ea1ff" stroke-width="2.2" fill="none" stroke-linecap="round"/>',
  img:'<rect x="3.5" y="5" width="17" height="14" rx="2" stroke="#f5b84a" stroke-width="2" fill="none"/><circle cx="9" cy="10" r="1.6" fill="#f5b84a"/><path d="m5 17 5-5 3 3 2-2 4 4" stroke="#f5b84a" stroke-width="2" fill="none"/>',
  escudo:'<path d="M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-5.5 7-10V6l-7-3z" stroke="#3ecf8e" stroke-width="2" fill="none"/><path d="m9 12 2 2 4-4" stroke="#3ecf8e" stroke-width="2" fill="none"/>',
  brilho:'<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM18 15l.8 2.2L21 18l-2.2.8L18 21l-.8-2.2L15 18l2.2-.8z" fill="#b38cff"/>',
  doc:'<path d="M7 3h7l5 5v13H7z" stroke="#c9c9d3" stroke-width="2" fill="none"/><path d="M14 3v5h5M10 13h6m-6 4h6" stroke="#c9c9d3" stroke-width="2"/>',
  banco:'<ellipse cx="12" cy="6" rx="7" ry="3" stroke="#8fa3b8" stroke-width="2" fill="none"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3" stroke="#8fa3b8" stroke-width="2" fill="none"/>',
  chat:'<path d="M4 5h16v11H9l-5 4z" stroke="#b38cff" stroke-width="2" fill="none" stroke-linejoin="round"/><path d="M8 10h8M8 13h5" stroke="#b38cff" stroke-width="2"/>',
};
const svg = n => `<svg viewBox="0 0 24 24">${ICONES[n]}</svg>`;
const COR = {ok:"var(--ok)", alerta:"var(--alerta)", falha:"var(--falha)", interrompida:"var(--falha)", rodando:"var(--rodando)",
  aguardando_ia:"var(--ia)", "aguardando IA":"var(--ia)", pulada:"#6b6b75", migrado:"#d29a3c", incompleto:"#8a8a94", "sem dados":"#8a8a94",
  concluida:"var(--ok)", falhou:"var(--falha)"};
const DICA_STATUS = {
  "ok": "Concluído: todas as etapas terminaram e as checagens do programa passaram.",
  "alerta": "Concluído com alerta: terminou, mas alguma checagem pede conferência (ex.: citação não encontrada, trecho sem fala).",
  "falha": "Falha: alguma etapa não terminou. O erro está em ‘Falhas e alertas’.",
  "aguardando IA": "Aguardando a IA: o programa fez a parte dele; o pacote espera a resposta do Claude/ChatGPT no chat.",
  "migrado": "Importado do histórico: veio da fase anterior (ChatGPT/Codex). Os dados estão no banco, mas NÃO passaram por este programa — por isso não têm etapas nem checagens registradas. Para ter rastreio completo, é preciso reprocessar.",
  "incompleto": "Incompleto: alguma etapa foi pulada (o motivo está registrado).",
  "rodando": "Em processamento agora.",
  "sem dados": "Registrado sem etapas.",
};
const ROTULO = {"ok":"concluídos", "alerta":"com alerta", "falha":"com falha", "aguardando IA":"aguardando IA", "migrado":"importados do histórico",
  "incompleto":"incompletos", "rodando":"em processamento", "sem dados":"sem dados"};
function pill(st, txt){ const s = String(st || "sem"); const cls = s.startsWith("aguardando") ? "aguardando" : s.split(" ")[0];
  return `<span class="pill p-${esc(cls)}">${esc(txt ?? s)}</span>`; }


// ===== vocabulário único de situação (vem do motor de números do servidor) =====
const SIT_COR = {"rodando":"var(--rodando)","sem sinal":"var(--falha)","falha":"var(--falha)","bloqueado":"#d29a3c","aguardando IA":"var(--ia)",
  "alerta":"var(--alerta)","incompleto":"#8a8a94","concluído":"var(--ok)","na fila":"#8fa3b8","migrado":"#d29a3c"};
const EXPLICA = {};
function chipsSituacao(sit, ordem){
  return (ordem||Object.keys(SIT_COR)).filter(k => sit[k]).map(k => `<span class="chip-st" style="background:#2e2e33;color:${SIT_COR[k]||"#ccc"}" data-dica="${esc(EXPLICA[k]||k)}">${sit[k]} ${esc(k)}</span>`).join("") || '<span class="sub">—</span>';
}
function chipsTexto(sit){ return Object.entries(sit||{}).filter(([,n])=>n).map(([k,n])=>`${n} ${k}`).join(' · ') || '—'; }
function guardarExplica(m){ if (m && m.explica) Object.assign(EXPLICA, m.explica); }

function semEmpilhar(nome, fn){ return async (...a) => { if (S["ocupado_"+nome]) return; S["ocupado_"+nome] = true; try { return await fn(...a); } finally { S["ocupado_"+nome] = false; } }; }
const S = {view:"workflow", execucao:null, timer:null, cam:null, arrastou:false, logFiltro:"todos"};
const BUILD='3.2.0';

// ------------------------------------------------------------- navegação
document.querySelectorAll("nav a").forEach(a => a.onclick = () => ir(a.dataset.v));
function ir(v, arg){
  S.hPagina = null;
  S.view = v; const h = "#" + (arg ? `${v}/${arg}` : v); S._rot = h; if (location.hash !== h) history.replaceState(null, "", h);
  document.querySelectorAll("nav a").forEach(a => a.classList.toggle("ativo", a.dataset.v === v));
  fecharGaveta(); clearInterval(S.timer); clearInterval(S.timerFontes);S.timer=null;
  ({workflow:vWorkflow, videos: arg ? () => vVideo(arg) : vVideos, execucoes:vExecucoes, falhas:vFalhas, banco:vBanco}[v] || vWorkflow)();
}
function fecharGaveta(){ $("#gaveta").classList.add("fechada"); }
function abrirGaveta(html){ $("#gavetaConteudo").innerHTML = html; $("#gaveta").classList.remove("fechada"); }
function ampliar(src){ $("#lightboxImg").src = src; $("#lightbox").classList.add("aberta"); }
const TXT_IA = "Interprete os vídeos pendentes em S:\\CV (a lista está em dados/PENDENTES_IA.md)";
function copiarIA(){ navigator.clipboard?.writeText(TXT_IA); }
function faixaIA(n){
  if (!n || localStorage.getItem('aviso-ia-oculto')) return "";
  return `<div class="faixa-ia">${svg("chat")}<div><b>${n} vídeo(s) aguardando a IA.</b> Pacotes válidos na biblioteca. Peça no chat (Claude ou ChatGPT):
    <code>${esc(TXT_IA)}</code>. Quando a resposta chegar, o painel importa e confere sozinho.</div><button onclick="copiarIA()">copiar</button><button aria-label="Fechar aviso da IA" onclick="localStorage.setItem('aviso-ia-oculto','1');this.closest('.faixa-ia').remove()">×</button></div>`;
}

// ------------------------------------------------------------- WORKFLOW
function vWorkflow(){
  $("#principal").innerHTML = `
    <div class="topo"><h1>Workflow</h1><span id="vivo" class="vivo">Sem operação</span>
      <div class="dir"><button onclick="S.manual=false;S.execucao=null;atualizarWorkflow()">Acompanhar atual</button><select id="selExec" title="Escolha qual execução mostrar"></select></div></div>
    <div id="faixaIA"></div><div id="progressoGlobal"></div>
    <div class="linha-status" id="linhaStatus"><span class="msg">carregando…</span></div>
    <div class="palco" id="palco">
      <div class="mundo" id="mundo"><div class="camada" id="camada"></div></div>
      <div class="zoom"><button onclick="zoomPor(1.2)" title="aproximar">+</button><button onclick="zoomPor(1/1.2)" title="afastar">−</button><button onclick="enquadrar()" title="centralizar">⤢</button></div>
      <div class="dica-palco">Linhas contínuas: etapas. Tracejadas: registros e troca de arquivos com a IA; sem indicar tráfego ao vivo. Arraste para mover · roda para zoom · clique para conferir.</div>
    </div>`;
  $("#selExec").onchange = e => { S.execucao = e.target.value; S.manual=true; atualizarWorkflow(); };
  prepararPalco();
  atualizarWorkflow();
  S.timer = setInterval(atualizarWorkflow, 1500);
}

function prepararPalco(){
  const palco = $("#palco"), mundo = $("#mundo");
  S.aplicarCam = () => { mundo.style.transform = `translate(${S.cam.x}px,${S.cam.y}px) scale(${S.cam.k})`;
    palco.style.backgroundPosition = `${S.cam.x}px ${S.cam.y}px`; palco.style.backgroundSize = `${20*S.cam.k}px ${20*S.cam.k}px`; };
  if (!S.cam) enquadrar(); else S.aplicarCam();
  let ini = null;
  palco.addEventListener("pointerdown", e => { if (e.target.closest(".zoom")) return; ini = {x:e.clientX, y:e.clientY, cx:S.cam.x, cy:S.cam.y}; S.arrastou = false; });
  palco.addEventListener("pointermove", e => { if (!ini) return; const dx = e.clientX - ini.x, dy = e.clientY - ini.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) { S.arrastou = true; palco.classList.add("arrastando"); }
    if (S.arrastou) { S.cam.x = ini.cx + dx; S.cam.y = ini.cy + dy; S.aplicarCam(); } });
  const soltar = () => { ini = null; palco.classList.remove("arrastando"); setTimeout(() => S.arrastou = false, 0); };
  palco.addEventListener("pointerup", soltar); palco.addEventListener("pointerleave", soltar);
  palco.addEventListener("wheel", e => { e.preventDefault(); const r = palco.getBoundingClientRect();
    zoomEm(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.1 : 1/1.1); }, {passive:false});
}
function zoomEm(mx, my, f){ const k2 = Math.min(2.5, Math.max(0.35, S.cam.k * f));
  S.cam.x = mx - (mx - S.cam.x) * (k2 / S.cam.k); S.cam.y = my - (my - S.cam.y) * (k2 / S.cam.k); S.cam.k = k2; S.aplicarCam(); }
function zoomPor(f){ const p = $("#palco"); zoomEm(p.clientWidth/2, p.clientHeight/2, f); }
function enquadrar(){ const palco = $("#palco"); if (!palco) return; const w = palco.clientWidth, h = palco.clientHeight, k = Math.min(1, (w - 40) / 1240, (h - 30) / 520);
  S.cam = {x: (w - 1240 * k) / 2, y: Math.max(10, (h - 520 * k) / 2), k}; S.aplicarCam(); }

function estadoAgregado(a){
  if (!a || !a.total) return "vazio";
  for (const s of ["sem_sinal","rodando","falha","interrompida","aguardando_ia","bloqueada","alerta","pulada"]) if (a[s]) return s === "interrompida" ? "falha" : s;
  return "ok";
}

const atualizarWorkflow = semEmpilhar('workflow', async function(){
  const q = S.manual && S.execucao ? `?execucao=${S.execucao}` : "";
  let d; try { d = await api(`/api/painel${q}`); } catch { const v = $("#vivo"); if (v) v.textContent = "servidor desligado"; return; }
  if (S.view !== "workflow" || !$("#camada")) return;
  if (!S.manual && d.execucao) S.execucao = d.execucao.id;
  const sel = $("#selExec");
  const origem = x => ({importacao_ia:" · importação da IA", migracao:" · migração", painel:" · pelo painel", terminal:" · pelo terminal"}[x.disparada_por] || "");
  const opts = d.execucoes.map(x => `<option value="${x.id}" ${x.id===S.execucao?"selected":""}>${dataCurta(x.inicio)} · lote ${d.execucoes.length-d.execucoes.indexOf(x)} · ${x.status==='concluida'?'concluído':esc(x.status)}${origem(x)} · ${x.total_entradas} entradas</option>`).join("");
  if (sel.dataset.h !== opts){ sel.innerHTML = opts || "<option>nenhuma execução ainda</option>"; sel.dataset.h = opts; }
  const vivo = $("#vivo"); vivo.className = "vivo" + (d.vivo ? " on" : ""); vivo.textContent = estadoOperacao(d);
  $("#faixaIA").innerHTML = faixaIA(d.m.ia.prontos);
  if($('#progressoGlobal'))$('#progressoGlobal').innerHTML=progressoGlobal(d);
  const atual = d.fila.find(v => v.status === "rodando") || null;
  const idx = atual ? d.fila.indexOf(atual) + 1 : 0;
  $("#linhaStatus").innerHTML = d.vivo
    ? `<b class="s-rodando">Vídeo ${idx || "?"} de ${d.execucao.total_entradas}</b> · ${esc(NOME[atual?.atual] || "")} <span class="msg">${d.ultimo ? esc(d.ultimo.mensagem) : ""}</span>`
    : d.execucao ? `<span>Resultado:</span> <span class="msg">Lote: ${d.m.lote?.videos||0} vídeo(s) · ${chipsTexto(d.m.lote?.situacao)}</span> <a style="margin-left:auto;white-space:nowrap" onclick="ir('execucoes')">registro completo →</a>`
    : `<span class="msg">Nenhuma execução ainda. Envie um vídeo na aba Vídeos.</span>`;
  desenharFluxo(d);
});

function desenharFluxo(d){
  if (!d.m) { $("#linhaStatus").innerHTML = '<span class="s-falha">O servidor em execução é uma versão antiga. Feche as janelas pretas do painel e abra o ABRIR_PAINEL.bat.</span>'; return; }
  const m = d.m; guardarExplica(m);
  const L = m.lote || {videos:0, etapas:{}, recusadas:[], situacao:{}};
  const W = 132, H = 104, Y = 50, X0 = 20, PASSO = 172;
  const nos = [{id:"entrada", nome:"Entrada", icone:"entrada"}, ...ETAPAS].map((e, i) => ({...e, x: X0 + i * PASSO, y: Y}));
  const total = L.videos;
  const est = id => { const a = L.etapas[id]; if (!a || !total || a.nao_rodou === total) return "vazio";
    if (a.rodando) return "rodando"; if (a.falha) return "falha"; if (a.bloqueada) return "bloqueada"; if (a.aguardando) return "aguardando_ia";
    if (a.alerta) return "alerta"; if (a.pulada) return "pulada"; return a.feito === total ? "ok" : "vazio"; };
  let ar = "";
  for (let i = 0; i < nos.length - 1; i++){
    const a = nos[i], b = nos[i+1], stb = est(b.id);
    const cls = stb === "rodando" ? "ativa" : stb === "aguardando_ia" ? "ia" : stb !== "vazio" ? "feita" : "";
    ar += `<path class="aresta ${cls}" d="M${a.x+W} ${a.y+H/2} C${a.x+W+20} ${a.y+H/2}, ${b.x-20} ${b.y+H/2}, ${b.x} ${b.y+H/2}"/>`;
  }
  const banco = {x: X0 + 2.5 * PASSO, y: 330}, chat = {x: X0 + 5 * PASSO, y: 330};
  for (const i of [1,2,3,4,6]) { const x=nos[i].x+W/2, bx=banco.x+W/2, y=205+i*13; ar+=`<path class="aresta dados" d="M${x} ${Y+H+40} V${y} H${bx} V${banco.y}"/>`; }
  const ix=nos[5].x+W/2, cx=chat.x+W/2;
  ar+=`<path class="aresta dados vinculo-ia" d="M${ix} ${Y+H+40} V300 H${cx} V${chat.y}"/>`;
  const html = nos.map(n => {
    if (n.id === "entrada") return `<div class="no2 ${total?"ok":"vazio"}" style="left:${n.x}px;top:${n.y}px" onclick="if(!S.arrastou)ir('videos')" data-dica="Entradas deste lote: ${L.entradas||0}. Aceitas como vídeo: ${total}. Recusadas: ${L.recusadas.length}${L.recusadas.length?' — '+esc(L.recusadas.join(' | ')):''}">
      <div class="caixa">${svg("entrada")}<span class="num">${total} vídeo(s)</span></div><div class="rot">Entrada</div><div class="sub2">${L.recusadas.length ? `<span class="s-falha">${L.recusadas.length} recusado(s)</span>` : "&nbsp;"}</div></div>`;
    const a = L.etapas[n.id] || {}, st = est(n.id);
    const selo = {ok:"✓", alerta:"!", falha:"×", rodando:"…", aguardando_ia:"?", pulada:"–", bloqueada:"!"}[st] || "";
    const partes = [a.falha ? `${a.falha} com falha` : "", a.alerta ? `${a.alerta} com alerta` : "", a.pulada ? `${a.pulada} pulada(s)` : "",
                    a.aguardando ? `${a.aguardando} aguardando IA` : "", a.bloqueada ? `${a.bloqueada} bloqueado(s)` : "", a.rodando ? "rodando" : ""].filter(Boolean);
    const sub = !total ? "—" : a.nao_rodou === total ? (d.vivo ? "na fila" : "não rodou") : (partes.join(" · ") || "tudo certo");
    const barras = (L.lista||[]).map(v => `<i class="${v.etapas[n.id] || ""}"></i>`).join("");
    return `<div class="no2 ${st}" style="left:${n.x}px;top:${n.y}px" onclick="if(!S.arrastou)detalheEtapa('${n.id}')" data-dica="${esc(n.explica)} Número = vídeos deste lote com a etapa feita (estado atual).">
      <div class="caixa">${svg(n.icone)}<span class="num">${total ? `${a.feito||0}/${total}` : "—"}</span>${total > 1 && total <= 30 ? `<span class="minibarra">${barras}</span>` : ""}
      ${selo ? `<span class="anel">${selo}</span>` : ""}</div><div class="rot">${n.nome}</div><div class="sub2">${esc(sub)}</div></div>`;
  }).join("");
  const nIA = m.ia.prontos;
  $("#camada").innerHTML = `<svg>${ar}</svg>${html}
    <div class="no2" style="left:${banco.x}px;top:${banco.y}px" onclick="if(!S.arrastou)ir('banco')" data-dica="Biblioteca inteira (dados/cv.db).">
      <div class="caixa">${svg("banco")}<span class="num">${m.biblioteca.videos} vídeos</span></div><div class="rot">Banco de dados</div>
      <div class="sub2">biblioteca inteira</div></div>
    <div class="no2 ${nIA ? "aguardando_ia" : ""}" style="left:${chat.x}px;top:${chat.y}px" data-dica="Biblioteca inteira: ${nIA} pacote(s) prontos para a IA do chat; ${m.ia.bloqueados} bloqueado(s) (precisam reprocessar).">
      <div class="caixa">${svg("chat")}<span class="num">${nIA} prontos</span></div><div class="rot">IA do chat</div><div class="sub2">biblioteca inteira</div></div>`;
}

async function detalheEtapa(id){
  const et = ETAPAS.find(x => x.id === id);
  if (!S.execucao) return;
  const r = await api(`/api/etapa?execucao=${S.execucao}&etapa=${id}`);
  const prob = r.checagens.filter(c => c.status !== "ok");
  abrirGaveta(`<h2>${et.nome} <span class="quem ${et.quem}">${et.quem === "ia" ? "IA" : "PROGRAMA"}</span></h2>
    <p class="sub">${esc(et.explica)}</p>
    <h3>Situação nesta execução</h3>
    ${r.videos.map(v => `<div class="proc"><div class="pinfo"><div class="tit">${esc(v.titulo)}</div><div class="orig">${esc(v.mensagem || "")}</div></div>${pill(v.status)}</div>`).join("") || `<div class="vazio">Nenhum vídeo.</div>`}
    <h3>Checagens com problema (${prob.length} de ${r.checagens.length})</h3>
    ${prob.length ? prob.map(c => `<div class="rec"><div class="cab">${pill(c.status)} <b>${esc(c.nome)}</b></div>esperado <b>${esc(c.esperado)}</b> · obtido <b>${esc(c.obtido)}</b><br><small class="sub">${esc(c.explicacao || "")}</small></div>`).join("") : `<p class="sub">${r.checagens.length?'As checagens registradas passaram.':'Não há checagens registradas neste recorte; isso não significa aprovação.'}</p>`}
    <details><summary>Eventos registrados (${r.eventos.length})</summary><div class="log">${r.eventos.map(linhaLog).join("")}</div></details>`);
}
function linhaLog(e){
  return `<div class="ev-${esc(e.tipo)} ev-${esc(e.status)}"><span class="t">${hora(e.ts)}</span> <span class="e">${e.etapa ? "["+esc(NOME[e.etapa]||e.etapa)+"] " : ""}${esc(e.mensagem)}</span></div>`;
}

// ------------------------------------------------------------- VÍDEOS (por fonte)
function vVideos(){
  S.periodo=S.periodo||'hoje';
  $("#principal").innerHTML = `<div class="topo"><h1>Vídeos</h1><div class="dir" id="acoesVideos"></div></div>
    <section class="bloco entrada-compacta" aria-label="Adicionar vídeos">
      <div id="soltar" class="soltar" role="button" tabindex="0" aria-label="Escolher vídeos"><b>＋ Adicionar vídeos</b><small>Escolher ou arrastar arquivos</small></div>
      <input type="file" id="arquivos" accept="video/*" multiple hidden>
      <textarea id="links" rows="1" aria-label="Links dos vídeos" placeholder="Ou cole links, um por linha"></textarea>
      <button class="prim" id="btnProcessar" onclick="processar()">Processar</button>
      <div id="enviados" class="enviados"></div><span id="msgProc" class="sub"></span>
    </section>
    <section class="bloco"><div class="cab-resumo"><h2>Agora <small class="sub">· biblioteca inteira</small></h2><span class="sub" id="confMini"></span></div><div id="agora"></div></section>
    <div id="faixaIA"></div><div id="funil"></div>
    <section class="bloco processamento-compacto"><h2 id="tituloProc">Último processamento</h2><div id="emProc"></div></section>
    <div class="cab-resumo"><h2>De onde vêm os vídeos</h2><small class="sub">biblioteca inteira · mesmos números do bloco “Agora”</small></div><div id="fontes"></div>
    <button class="aviso-discreto" onclick="localStorage.removeItem('aviso-ia-oculto');atualizarVideos()">Mostrar aviso da IA</button>`;
  const zona = $("#soltar"), inp = $("#arquivos");
  zona.onclick = () => inp.click();
  zona.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();inp.click();}};
  inp.onchange = () => adicionarArquivos(inp.files);
  zona.ondragover = e => { e.preventDefault(); zona.classList.add("sobre"); };
  zona.ondragleave = () => zona.classList.remove("sobre");
  zona.ondrop = e => { e.preventDefault(); zona.classList.remove("sobre"); adicionarArquivos(e.dataTransfer.files); };
  S.enviados = S.enviados || [];
  $('#enviados').textContent=S.enviados.length?`${S.enviados.length} arquivo(s) enviado(s), aguardando Processar`:'';
  $('#btnProcessar').disabled=!!(S.uploads||S.enviando);
  atualizarVideos();
  S.timer = setInterval(atualizarVideos, 2000);
}
async function adicionarArquivos(lista){
  S.uploads=(S.uploads||0)+1;$("#btnProcessar").disabled=true;
  try { for (const f of lista){
    const linha = document.createElement("div"); linha.textContent = `↑ enviando ${f.name} (${(f.size/1e6).toFixed(1)} MB)…`; $("#enviados").appendChild(linha);
    try { const r = await (await fetch(`/api/enviar?nome=${encodeURIComponent(f.name)}`, {method:"POST", body:f})).json();
      if (r.erro) throw new Error(r.erro);
      S.enviados.push(r.arquivo); linha.innerHTML = `<span class="s-ok">✓</span> ${esc(f.name)} pronto (${r.tamanho_mb} MB) — clique em Processar`; }
    catch (e) { linha.innerHTML = `<span class="s-falha">×</span> ${esc(f.name)}: ${esc(e.message)}`; }
  }
  } finally {S.uploads--;if($("#btnProcessar"))$("#btnProcessar").disabled=!!S.uploads;}
}
async function processar(){
  if(S.enviando||S.uploads)return;S.enviando=true;$("#btnProcessar").disabled=true;
  try{
  const r = await api("/api/processar", {links: $("#links").value, arquivos: S.enviados});
  if (r.erro) return $("#msgProc").innerHTML = `<span class="s-falha">${esc(r.erro)}</span>`;
  $("#msgProc").innerHTML = r.ja_agendado ? '<span>Esses vídeos já estão no lote ativo ou na fila. Nenhum pedido duplicado foi criado.</span>' : r.na_espera
    ? `<span class="s-aguardando">Já há um processamento rodando. Seus ${r.videos} vídeo(s) entraram na fila de espera (${r.lotes_na_espera} lote(s)) e começam sozinhos quando o atual terminar.</span>`
    : `<span class="s-ok">Iniciado: ${r.videos} vídeo(s). Acompanhe abaixo ou no Workflow.</span>`;
  S.enviados = []; $("#enviados").innerHTML = ""; $("#links").value = ""; S.execucao = null;
  }catch(e){$('#msgProc').textContent=e.message;}finally{S.enviando=false;if($("#btnProcessar"))$("#btnProcessar").disabled=!!S.uploads;}
}
function donut(partes, centro){
  const tot = partes.reduce((a,p) => a + p.v, 0) || 1; let ac = 0; const R = 42, C = 2 * Math.PI * R;
  const arcos = partes.filter(p => p.v).map(p => { const l = C * p.v / tot; const s = `<circle r="${R}" cx="55" cy="55" fill="none" stroke="${p.c}" stroke-width="14" stroke-dasharray="${l} ${C-l}" stroke-dashoffset="${-ac}" transform="rotate(-90 55 55)"/>`; ac += l; return s; }).join("");
  return `<svg viewBox="0 0 110 110"><circle r="${R}" cx="55" cy="55" fill="none" stroke="#3a3a40" stroke-width="14"/>${arcos}
    <text x="55" y="55" text-anchor="middle" fill="#e9e9ee" font-size="18" font-weight="700">${centro[0]}</text><text x="55" y="70" text-anchor="middle" fill="#9a9aa6" font-size="10">${centro[1]}</text></svg>`;
}
const atualizarVideos = semEmpilhar('videos', async function(){
  let d; try { d = await api("/api/painel"); } catch { return; }
  const m = d.m; guardarExplica(m);
  const n = (m.lote?.situacao?.rodando) || 0; $("#nproc").textContent = d.vivo ? (n || "•") : "";
  if (S.view !== "videos" || !$("#emProc")) return;
  $("#faixaIA").innerHTML = faixaIA(m.ia.prontos) + controleFila(d);
  // AGORA (biblioteca)
  const b = m.biblioteca, E = b.etapas;
  const passo = (t, id, extra) => `<div class="fcx" data-dica="${esc(extra||'')}"><span class="ft">${t}</span><b>${E[id].feito}</b><span class="fde">de ${b.videos}</span>${E[id].falha?`<span class="ff">${E[id].falha} falha(s)</span>`:''}</div>`;
  $("#agora").innerHTML = `<div class="agora-topo"><div class="agora-total"><b>${b.videos}</b><span>vídeos na biblioteca</span></div><div class="agora-chips">${chipsSituacao(b.situacao, m.ordem_situacoes)}</div></div>
    <div class="flinha">${passo("Baixados","baixar")}<i class="seta">→</i>${passo("Transcritos","transcrever")}<i class="seta">→</i>${passo("Imagens","imagens")}<i class="seta">→</i>${passo("Conferidos","integridade")}<i class="seta">→</i>
      <div class="fcx" data-dica="Pacotes válidos esperando a IA do chat."><span class="ft">Prontos p/ IA</span><b>${m.ia.prontos}</b><span class="fde">de ${b.videos}</span>${m.ia.bloqueados?`<span class="ff">${m.ia.bloqueados} bloqueado(s)</span>`:''}</div><i class="seta">→</i>
      ${passo("Interpretados","interpretar","Respostas da IA importadas e conferidas.")}</div>
    <p class="sub" style="margin:8px 0 0">Migrados da fase anterior não têm etapas deste programa, por isso não entram nos números das etapas.</p>`;
  const conf = d.conferencia || [], ruins = conf.filter(c => !c.ok);
  $("#confMini").innerHTML = ruins.length ? `<span class="s-falha" data-dica="${esc(ruins.map(c=>`${c.nome}: ${c.valor} ≠ ${c.esperado}`).join(' | '))}">✗ ${ruins.length} número(s) não batem</span>`
                                          : `<span class="s-ok" data-dica="${esc(conf.map(c=>c.nome).join(' · '))}">✓ números conferidos (${conf.length} checagens)</span>`;
  // LOTE
  $("#funil").innerHTML = funil(d);
  $("#acoesVideos").innerHTML = b.situacao.falha ? `<button ${d.vivo?'disabled':''} onclick="reprocessarFalhas()" data-dica="Roda de novo só as etapas que falharam. O que já deu certo (ex.: download) é mantido.">${d.vivo?'Processamento em andamento':`↻ Reprocessar ${b.situacao.falha} vídeo(s) com falha`}</button>` : "";
  const L = m.lote, ex = d.execucao;
  $("#tituloProc").textContent = d.vivo ? "Em processamento agora" : "Vídeos do último lote";
  if (!L || !L.lista.length) $("#emProc").innerHTML = `<div class="vazio">Nada processado ainda. Adicione vídeos acima.</div>`;
  else {
    const prep = Object.fromEntries((d.fila||[]).map(v => [v.video_id, v.preparacao_pct]));
    const abertos=$('#listaVideos')?.open||false, rolagem=$('.lista-videos')?.scrollTop||0;
    const linhas=L.lista.map((v,i)=>`<tr class="clic" onclick="ir('videos','${esc(v.video_id)}')"><td>${i+1}</td><td class="titulo-video" title="${esc(v.titulo)}">${esc(v.titulo)}</td><td>${esc(v.rede)} · ${esc(v.perfil)}</td><td><span style="color:${SIT_COR[v.situacao]}" data-dica="${esc(EXPLICA[v.situacao]||'')}">${esc(v.situacao)}</span></td><td><span class="seg mini">${ETAPAS.map(e=>`<i class="${v.etapas[e.id]||''}" data-dica="${esc(e.nome)}: ${esc(v.etapas[e.id]||'ainda não')}"></i>`).join('')}</span></td><td>${Math.round(prep[v.video_id]||0)}%</td></tr>`).join('');
    $('#emProc').innerHTML=progressoGlobal(d)+`<div class="resumo-lote"><b>${L.videos} vídeo(s)</b><span>${chipsTexto(L.situacao)}</span><span>${dataCurta(L.inicio)}</span><a onclick="ir('execucoes')">Ver registros →</a></div>
      <details id="listaVideos" ${abertos||d.vivo?'open':''}><summary>Ver os ${L.videos} vídeos deste lote</summary><div class="tab-wrap lista-videos"><table><tr><th>#</th><th>Vídeo</th><th>Origem</th><th>Situação</th><th>Etapas</th><th>Preparação técnica</th></tr>${linhas}</table></div></details>`;
    if($('.lista-videos'))$('.lista-videos').scrollTop=rolagem;
  }
  // FONTES (mesmo snapshot)
  const redes={};for(const f of m.fontes)redes[f.rede]=(redes[f.rede]||0)+f.videos;
  $("#fontes").innerHTML = `<div class="totais-redes">${Object.entries(redes).map(([rede,k])=>`<span><b>${esc(rede)}</b> ${k} vídeos</span>`).join('')}</div>
    <div class="tab-wrap fontes" style="max-height:none;overflow:auto"><table><tr><th>Rede social</th><th>Perfil</th><th>Vídeos</th><th>Situação</th><th>Duração total</th><th>Atualizado</th></tr>
    ${m.fontes.map(f => `<tr><td><b>${esc(f.rede)}</b></td><td>${esc(f.perfil)}</td><td><b>${f.videos}</b></td><td>${chipsSituacao(f.situacao, m.ordem_situacoes)}</td><td>${fmt(f.duracao_s)}</td><td>${dataCurta(f.atualizado)}</td></tr>`).join("")
      || `<tr><td colspan="6"><div class="vazio">Nenhum vídeo ainda.</div></td></tr>`}
    <tr class="total"><td colspan="2"><b>Total</b></td><td><b>${m.fontes.reduce((a,f)=>a+f.videos,0)}</b></td><td colspan="3" class="sub">= ${b.videos} na biblioteca</td></tr></table></div>`;
});

function funil(d){
  const L = d.m.lote; if (!L) return "";
  const E = L.etapas, n = L.videos;
  const caixa = (t, id, dica) => `<div class="fcx" data-dica="${esc(dica)}"><span class="ft">${t}</span><b>${E[id].feito}</b><span class="fde">de ${n}</span>${E[id].falha?`<span class="ff">${E[id].falha} falha(s)</span>`:''}${E[id].pulada?`<span class="fx">${E[id].pulada} pulada(s)</span>`:''}</div>`;
  return `<div class="bloco funil"><div class="cab-funil"><h2>${d.vivo?"Lote atual":"Último lote"} <small class="sub">${dataCurta(L.inicio)} · ${estadoOperacao(d)} · estado atual dos vídeos deste lote</small></h2></div>
    <div class="flinha"><div class="fcx" data-dica="${esc(L.recusadas.length ? "Recusados: " + L.recusadas.join(" | ") : "Todas as entradas foram aceitas.")}"><span class="ft">Entradas</span><b>${L.entradas}</b><span class="fde">${n} aceitas como vídeo</span>${L.recusadas.length?`<span class="ff">${L.recusadas.length} recusada(s)</span>`:''}</div><i class="seta">→</i>
    ${caixa("Baixados","baixar","Vídeo baixado ou copiado e conferido.")}<i class="seta">→</i>${caixa("Transcritos","transcrever","Fala transformada em texto (Whisper).")}<i class="seta">→</i>
    ${caixa("Imagens","imagens","Imagens extraídas.")}<i class="seta">→</i>${caixa("Conferidos","integridade","Checagens de integridade concluídas.")}<i class="seta">→</i>
    <div class="fcx"><span class="ft">Prontos p/ IA</span><b>${E.interpretar.aguardando}</b><span class="fde">de ${n}</span>${E.interpretar.bloqueada?`<span class="ff">${E.interpretar.bloqueada} bloqueado(s)</span>`:''}</div><i class="seta">→</i>
    ${caixa("Interpretados","interpretar","Resposta da IA importada e conferida.")}</div></div>`;
}

function mudarPeriodo(){S.periodo=$('#periodo').value;S.dataResumo=$('#dataResumo').value;$('#dataResumo').hidden=!['data','mes'].includes(S.periodo);atualizarResumo();}
async function atualizarResumo(){
  const periodo=S.periodo||'hoje',data=S.dataResumo||$('#dataResumo')?.value||'';
  const chave=periodo+data;S.resumoChave=chave;
  try{
    const r=await api(`/api/resumo?periodo=${periodo}&data=${encodeURIComponent(data)}`);
    if(S.view!=='execucoes'||!$('#resumoPeriodo')||S.resumoChave!==chave)return;
    if(r.erro)throw Error(r.erro);
    const valores=[['Novos na biblioteca',r.novos],['Baixados / copiados',r.etapas.baixar],['Transcritos',r.etapas.transcrever],['Com imagens',r.etapas.imagens],['Conferidos',r.etapas.integridade],['Interpretados',r.etapas.interpretar]];
    $('#resumoPeriodo').innerHTML=`<div class="metricas-periodo">${valores.map(([t,n])=>`<div><b>${n}</b><span>${t}</span></div>`).join('')}</div><div class="nota-periodo"><span title="${esc(r.criterio)}">Conclusões por vídeo no período · inclui alertas · sem duplicar reprocessamentos</span><b>${r.total_biblioteca} vídeos na biblioteca</b></div>`;
    S.ultimoResumo=Date.now();
  }catch(e){if($('#resumoPeriodo'))$('#resumoPeriodo').textContent='Resumo indisponível: '+e.message;}
}
async function reprocessarFalhas(){
  const r = await api("/api/reprocessar_falhas", {});
  alertaTopo(r.erro ? `<span class="s-falha">${esc(r.erro)}</span>` : r.na_espera ? `${r.videos} vídeo(s) com falha entraram na fila de espera.` : `Reprocessando ${r.videos} vídeo(s) com falha. Acompanhe abaixo.`);
}
function alertaTopo(html){ const m = $("#msgProc") || $("#msgFalhas"); if (m) m.innerHTML = html; }

async function carregarFontes(){
  const r = await api("/api/fontes");
  if (S.view !== "videos" || !$("#fontes")) return;
  const ordem = ["ok","alerta","falha","aguardando IA","rodando","incompleto","migrado","sem dados"];
  const redes={};for(const f of r.fontes)redes[f.rede]=(redes[f.rede]||0)+f.videos;
  $("#fontes").innerHTML = `<div class="totais-redes">${Object.entries(redes).map(([rede,n])=>`<span><b>${esc(rede)}</b> ${n} vídeos</span>`).join('')}</div><div class="tab-wrap fontes" style="max-height:none;overflow:auto"><table><tr><th>Rede social</th><th>Perfil</th><th>Vídeos</th><th>Status</th>
      <th data-dica="Registros de checagens com alerta/falha. Um vídeo pode ter vários registros. Detalhes em ‘Falhas e alertas’.">Checagens com aviso/falha</th>
      <th data-dica="Trechos de fala transcritos. 0 = nenhuma fala reconhecida no áudio (vídeo só com imagem ou música).">Falas</th>
      <th data-dica="Total de posições amostradas, incluindo repetições registradas. As imagens únicas guardadas podem ser abertas na ficha do vídeo.">Amostras de imagem</th><th>Duração total</th><th>Atualizado</th></tr>
    ${r.fontes.map(f => `<tr><td><b>${esc(f.rede)}</b></td><td>${esc(f.perfil)}</td><td><b>${f.videos}</b></td>
      <td>${ordem.filter(s => f.status[s]).map(s => `<span class="chip-st" style="background:#2e2e33;color:${COR[s]||"#ccc"}" data-dica="${esc(DICA_STATUS[s]||s)}">${f.status[s]} ${esc(ROTULO[s]||s)}</span>`).join("")}</td>
      <td>${f.problemas ? `<span class="s-alerta">${f.problemas}</span>` : "0"}</td><td>${f.falas}</td><td>${f.imagens}</td><td>${fmt(f.duracao_s)}</td><td>${dataCurta(f.atualizado)}</td></tr>`).join("")
      || `<tr><td colspan="9"><div class="vazio">Nenhum vídeo ainda.</div></td></tr>`}</table></div>`;
}

// ficha de um vídeo (aberta ao clicar num item em processamento)
async function vVideo(id, aba = "resumo"){
  const d = await api(`/api/video?id=${encodeURIComponent(id)}`);
  if(S.view!=='videos')return;
  if (d.erro) return $("#principal").innerHTML = `<div class="vazio">${esc(d.erro)}</div>`;
  const v = d.video;
  const abas = [["resumo","Etapas e checagens"],["transcricao",`Transcrição (${d.falas.length})`],["imagens",`Imagens (${d.frames.filter(f=>f.arquivo).length})`],["cv",`CV lido (${d.cv_exemplos.length})`]];
  $("#principal").innerHTML = `<p><a onclick="ir('videos')">← Vídeos</a></p><h1>${esc((v.titulo || v.video_id).split(" #")[0].slice(0,90))}</h1>
    <p class="sub">${fmt(v.duracao_s)} · ${pill(d.status)} · ${v.url ? `<a href="${esc(v.url)}" target="_blank">abrir original</a>` : "sem link de origem"}</p>
    <div class="abas">${abas.map(([k,n]) => `<a class="${k===aba?"ativo":""}" onclick="vVideo('${esc(id)}','${k}')">${n}</a>`).join("")}</div><div id="conteudoAba"></div>`;
  const el = $("#conteudoAba");
  if (aba === "resumo"){
    el.innerHTML = `${(v.origem||"").startsWith("migrado") ? `<div class="aviso">${esc(DICA_STATUS.migrado)}</div>` : ""}
      <table><tr><th>etapa</th><th>status</th><th>resultado</th><th>quando</th></tr>${ETAPAS.map(e => { const x = d.etapas.find(y => y.etapa === e.id);
        return `<tr><td>${e.nome}</td><td>${pill(x?.status || "pendente", x?.status || "não rodou")}</td><td>${esc(x?.mensagem || "")}</td><td>${dataHora(x?.fim)}</td></tr>`; }).join("")}</table>
      <h2>Checagens</h2>${d.checagens.length ? `<table><tr><th>status</th><th>checagem</th><th>esperado</th><th>obtido</th></tr>${d.checagens.map(c => `<tr><td>${pill(c.status)}</td><td>${esc(c.nome)}<br><small class="sub">${esc(c.explicacao||"")}</small></td><td>${esc(c.esperado)}</td><td>${esc(c.obtido)}</td></tr>`).join("")}</table>` : `<div class="vazio">Sem checagens registradas.</div>`}`;
  } else if (aba === "transcricao"){
    el.innerHTML = d.falas.map(f => `<div class="fala"><span class="tm">${fmt(f.inicio_s)}–${fmt(f.fim_s)}</span><span>${esc(f.texto)}</span></div>`).join("") || `<div class="vazio">Sem fala transcrita.</div>`;
  } else if (aba === "imagens"){
    const fs = d.frames.filter(f => f.arquivo);
    el.innerHTML = `<div class="grade">${fs.map(f => `<figure class="${f.mostra_cv===1?"cv":""}" onclick="ampliar('${midia(f.arquivo)}')"><img loading="lazy" src="${midia(f.arquivo)}" alt=""><figcaption>${fmt(f.t_s)} · ${f.enviado_ia ? "no pacote da IA" : "não enviada à IA"}${f.mostra_cv===1?" · CV":""}</figcaption></figure>`).join("")}</div>`;
  } else {
    el.innerHTML = d.cv_exemplos.map(c => `<div class="rec"><div class="cab"><b>${esc(c.secao)}</b> · legibilidade: ${esc(c.legibilidade)}</div><pre style="white-space:pre-wrap;margin:0;font-family:var(--mono);font-size:12.5px">${esc(c.texto_lido)}</pre></div>`).join("") || `<div class="vazio">Nenhum trecho de CV lido.</div>`;
  }
}

// ------------------------------------------------------------- EXECUÇÕES (analítico)
async function vExecucoes(){
  if(!S.timer)S.timer=setInterval(()=>{if(!$('#gaveta')?.classList.contains('fechada')||document.activeElement?.closest?.('.filtro-periodo')||$('#detExec')?.innerHTML)return;vExecucoes();},8000);
  const r = await api("/api/analitico"), k = r.kpis, rv = r.resultado_videos;
  if(S.view!=='execucoes')return;
  if (!r.agora) { $('#principal').innerHTML = '<div class="aviso">O servidor em execução é uma versão antiga. Feche as janelas pretas do painel e abra o ABRIR_PAINEL.bat.</div>'; return; }
  const A = r.agora.biblioteca;
  { const h = JSON.stringify(r); if (S.hPagina === 'exec:' + h) return; S.hPagina = 'exec:' + h; }
  const perAberto = $('#periodo') ? null : true;
  const maxT = Math.max(1, ...Object.values(r.tempo_etapa).map(x => x.media_s));
  const ordemSt = ["ok","alerta","falha","interrompida","pulada","bloqueada","sem_sinal","aguardando_ia","rodando"];
  const dias = Object.entries(r.por_dia).slice(-14), maxD = Math.max(1, ...dias.map(([,v]) => Object.values(v).reduce((a,b)=>a+b,0)));
  const soma = o => Object.values(o).reduce((a,b)=>a+b,0);
  $("#principal").innerHTML = `<div class="topo"><h1>Execuções e logs</h1></div>
    <h2 style="margin-top:4px">Agora <small class="sub">· biblioteca inteira (mesmos números da aba Vídeos)</small></h2>
    <div class="cards">
      <div class="card"><b>${A.videos}</b><span>vídeos na biblioteca</span></div>
      <div class="card" data-dica="${esc(r.explica['concluído'])}"><b class="s-ok">${A.situacao['concluído']}</b><span>concluídos</span></div>
      <div class="card" data-dica="${esc(r.explica['aguardando IA'])}"><b class="s-aguardando">${r.agora.ia.prontos}</b><span>prontos para a IA</span></div>
      <div class="card" data-dica="${esc(r.explica['falha'])}"><b class="${A.situacao.falha?'s-falha':''}">${A.situacao.falha}</b><span>com falha</span></div>
      <div class="card" data-dica="${esc(r.explica['bloqueado'])}"><b class="${A.situacao.bloqueado?'s-alerta':''}">${A.situacao.bloqueado}</b><span>bloqueados</span></div>
    </div>
    <h2>Histórico <small class="sub">· o que aconteceu ao longo do tempo</small></h2>
    <div class="cards">
      <div class="card" data-dica="Processamentos de vídeos (pelo painel ou terminal). Importações da IA: ${k.importacoes}. A migração não conta."><b>${k.execucoes}</b><span>processamentos</span></div>
      <div class="card" data-dica="Vídeos diferentes que já passaram pelo programa (reprocessar não duplica). Passagens no total: ${k.passagens}."><b>${k.videos_processados}</b><span>vídeos já processados</span></div>
      <div class="card" data-dica="Do início ao fim do processamento de um vídeo (sem contar a espera pela IA)."><b>${dur(k.tempo_medio_video_s)}</b><span>tempo médio por vídeo</span></div>
    </div>
    <section class="bloco resumo-periodo"><div class="cab-resumo"><h3>Atividade por período</h3><div class="filtro-periodo">
      <select id="periodo" onchange="mudarPeriodo()"><option value="hoje">Hoje</option><option value="mes">Mês da data</option><option value="data">Dia escolhido</option><option value="tudo">Todo o histórico</option></select>
      <input type="date" id="dataResumo" onchange="mudarPeriodo()"></div></div><div id="resumoPeriodo"></div></section>
    <div class="graficos">
      <div class="bloco"><h3>Resultado de cada passagem de vídeo <small class="sub">(um vídeo reprocessado aparece de novo)</small></h3><div class="donut">${donut([{v:rv.ok,c:"var(--ok)"},{v:rv["com alerta"],c:"var(--alerta)"},{v:rv["com falha"],c:"var(--falha)"},{v:rv["aguardando IA"],c:"var(--ia)"}], [k.passagens, "passagens"])}
        <div class="legenda"><span style="--c:var(--ok)">${rv.ok} ok</span><span style="--c:var(--alerta)">${rv["com alerta"]} com alerta</span><span style="--c:var(--falha)">${rv["com falha"]} com falha</span><span style="--c:var(--ia)">${rv["aguardando IA"]} aguardando IA</span></div></div></div>
      <div class="bloco barras"><h3>Tempo médio por etapa <small class="sub">(só quando a etapa rodou de verdade)</small></h3>
        ${ETAPAS.map(e => { const t = r.tempo_etapa[e.id]; return `<div class="lin"><span>${e.nome}</span><div class="trilho"><span style="width:${t ? 100*t.media_s/maxT : 0}%;background:var(--rodando)"></span></div><span class="val">${t ? dur(t.media_s) : "—"}</span></div>`; }).join("")}</div>
      <div class="bloco barras"><h3>Situação atual de cada etapa <small class="sub">(biblioteca, ${A.videos} vídeos)</small></h3>
        ${ETAPAS.map(e => { const x = A.etapas[e.id], t = A.videos || 1, partes = [["feito",x.feito-x.alerta,"var(--ok)"],["alerta",x.alerta,"var(--alerta)"],["falha",x.falha,"var(--falha)"],["aguardando IA",x.aguardando,"var(--ia)"],["bloqueado",x.bloqueada,"#d29a3c"],["pulada",x.pulada,"#6b6b75"],["rodando",x.rodando,"var(--rodando)"],["não rodou",x.nao_rodou,"#3a3a40"]];
          return `<div class="lin"><span>${e.nome}</span><div class="trilho">${partes.filter(p=>p[1]).map(p => `<span style="width:${100*p[1]/t}%;background:${p[2]}" data-dica="${p[1]} ${p[0]}"></span>`).join("")}</div><span class="val">${x.feito}/${A.videos}</span></div>`; }).join("")}</div>
      <div class="bloco"><h3>Execuções por dia</h3><div class="colunas">${dias.map(([dia,v]) => `<div class="col">${Object.keys(v).map(x => `<span style="height:${130*v[x]/maxD}px;background:${COR[x] || "#8a8a94"}" data-dica="${dia}: ${v[x]} ${x}"></span>`).join("")}</div>`).join("") || `<div class="vazio" style="width:100%">sem dados</div>`}</div>
        <div class="colunas rot" style="height:auto;border:none">${dias.map(([dia]) => `<span style="flex:1;max-width:60px;text-align:center">${dia.slice(8,10)}/${dia.slice(5,7)}</span>`).join("")}</div></div>
    </div>
    <h2>Todas as execuções</h2>
    <div class="tab-wrap"><table><tr><th>início</th><th>duração</th><th>status</th><th>itens</th><th>origem</th><th>resultado</th></tr>
    ${r.execucoes.map(x => `<tr class="clic" onclick="verExecucao('${x.id}')"><td>${dataHora(x.inicio)}</td><td>${dur(x.duracao_s)}</td><td>${pill(x.status)}</td><td>${x.total_entradas}</td>
      <td>${esc({painel:"painel", terminal:"terminal", importacao_ia:"importação da IA", migracao:"migração"}[x.disparada_por] || x.disparada_por)}</td><td>${esc(x.resumo || "")}</td></tr>`).join("") || `<tr><td colspan="6"><div class="vazio">Nenhuma execução.</div></td></tr>`}</table></div>
    <div id="detExec"></div>
    <h2>Erros e alertas recentes</h2><div class="log">${r.alertas.map(linhaLog).join("") || "<div>nenhum</div>"}</div>`;
  S.periodo=S.periodo||'hoje'; $('#periodo').value=S.periodo;
  $('#dataResumo').value=S.dataResumo||new Date().toLocaleDateString('en-CA',{timeZone:'America/Sao_Paulo'});
  $('#dataResumo').hidden=!['data','mes'].includes(S.periodo); atualizarResumo();
}
async function verExecucao(id){
  const r = await api(`/api/eventos?execucao=${id}`);
  S.logExec = r.eventos; S.logFiltro = "todos";
  desenharLogExec(id);
  $("#detExec").scrollIntoView({behavior:"smooth"});
}
function desenharLogExec(id){
  const evs = S.logFiltro === "problemas" ? S.logExec.filter(e => ["erro","alerta"].includes(e.tipo)) : S.logExec;
  $("#detExec").innerHTML = `<h2>Registro da execução</h2>
    <div class="filtros"><button class="${S.logFiltro==="todos"?"on":""}" onclick="S.logFiltro='todos';desenharLogExec('${id}')">todos (${S.logExec.length})</button>
      <button class="${S.logFiltro==="problemas"?"on":""}" onclick="S.logFiltro='problemas';desenharLogExec('${id}')">só erros e alertas</button>
      <button onclick="S.execucao='${id}';ir('workflow')">ver no workflow</button></div>
    <div class="log" style="max-height:55vh">${evs.map(linhaLog).join("") || "<div>nenhum</div>"}</div>`;
}

// ------------------------------------------------------------- FALHAS
async function vFalhas(){
  const r = await api("/api/falhas");
  if(S.view!=='falhas')return;
  { const h = JSON.stringify(r); if (S.hPagina === 'falhas:' + h) return; S.hPagina = 'falhas:' + h; }
  if(!S.timer)S.timer=setInterval(vFalhas,5000);
  const t = s => esc((s || "").split(" #")[0].slice(0,50));
  const totC = r.causas.reduce((a,c) => a + c.n, 0), totK = r.tipos_checagem.reduce((a,c) => a + c.n, 0);
  $("#principal").innerHTML = `<div class="topo"><h1>Falhas e alertas</h1><div class="dir"><span id="msgFalhas" class="sub"></span>${r.resumo_atual.videos_com_falha ? `<button onclick="reprocessarFalhas()">↻ Reprocessar ${r.resumo_atual.videos_com_falha} vídeo(s) com falha</button>` : ""}</div></div>
    <div class="cards"><div class="card"><b class="${r.resumo_atual.videos_com_falha?'s-falha':''}">${r.resumo_atual.videos_com_falha}</b><span>vídeos com falha (de ${r.resumo_atual.videos})</span></div>
      <div class="card"><b class="${r.resumo_atual.videos_com_alerta?'s-alerta':''}">${r.resumo_atual.videos_com_alerta}</b><span>vídeos com alerta</span></div>
      <div class="card"><b>${r.resumo_atual.videos_bloqueados}</b><span>vídeos bloqueados</span></div></div>
    <p class="sub">Mesmos números da aba Vídeos (recorte “Agora”). Abaixo: primeiro a <b>causa raiz</b>; depois as <b>consequências</b> (etapas que não rodaram porque uma anterior falhou).</p>
    <div class="grid2"><div class="bloco"><h2>Causa raiz: etapas que falharam (${totC})</h2>
      ${r.causas.length ? `<table><tr><th>vídeos</th><th>etapa</th><th>status</th><th>causa</th></tr>${r.causas.map(c => `<tr><td><b>${c.n}</b></td><td>${esc(NOME[c.etapa]||c.etapa)}</td><td>${pill(c.status)}</td><td>${esc(c.mensagem)}</td></tr>`).join("")}</table>` : `<div class="vazio">Nenhuma.</div>`}</div>
    <div class="bloco"><h2>Checagens com problema (${totK})</h2>
      ${r.tipos_checagem.length ? `<table><tr><th>vídeos</th><th>etapa</th><th>status</th><th>checagem</th></tr>${r.tipos_checagem.map(c => `<tr><td><b>${c.n}</b></td><td>${esc(NOME[c.etapa]||c.etapa)}</td><td>${pill(c.status)}</td><td>${esc(c.nome)}</td></tr>`).join("")}</table>` : `<div class="vazio">Nenhuma.</div>`}</div></div>
    <h2>Consequências <small class="sub">(não são erros novos)</small></h2>
    ${(r.consequencias||[]).length ? `<table><tr><th>vídeos</th><th>etapa</th><th>motivo</th></tr>${r.consequencias.map(c => `<tr><td><b>${c.n}</b></td><td>${esc(NOME[c.etapa]||c.etapa)}</td><td>${esc(c.mensagem)}</td></tr>`).join("")}</table>` : `<div class="vazio">Nenhuma.</div>`}
    <h2>Lista completa por vídeo (${r.etapas.length})</h2>
    ${r.etapas.length ? `<table><tr><th>vídeo</th><th>etapa</th><th>status</th><th>motivo</th><th>quando</th></tr>${r.etapas.map(e => `<tr><td>${t(e.titulo||e.video_id)}</td><td>${esc(NOME[e.etapa]||e.etapa)}</td><td>${pill(e.status)}</td><td>${esc(e.mensagem)}</td><td>${dataHora(e.fim)}</td></tr>`).join("")}</table>` : `<div class="vazio">Nenhuma.</div>`}
    <h2>Checagens com alerta ou falha (${r.checagens.length}) <small class="sub">— última execução de cada vídeo</small></h2>
    ${r.checagens.length ? `<table><tr><th>vídeo</th><th>status</th><th>checagem</th><th>esperado</th><th>obtido</th><th>explicação</th></tr>${r.checagens.map(c => `<tr><td>${t(c.titulo||c.video_id)}</td><td>${pill(c.status)}</td><td>${esc(c.nome)}</td><td>${esc(c.esperado)}</td><td>${esc(c.obtido)}</td><td>${esc(c.explicacao)}</td></tr>`).join("")}</table>` : `<div class="vazio">Nenhuma.</div>`}
    <h2>Citações da IA não encontradas na transcrição (${r.citacoes.length})</h2>
    ${r.citacoes.length ? `<table><tr><th>vídeo</th><th>tempo</th><th>citação</th><th>recomendação</th></tr>${r.citacoes.map(c => `<tr><td>${t(c.titulo||c.video_id)}</td><td>${fmt(c.inicio_s)}</td><td>${esc(c.citacao)}</td><td>${esc(c.recomendacao)}</td></tr>`).join("")}</table>` : `<div class="vazio">Nenhuma.</div>`}
    <h2>Execuções interrompidas ou que falharam (${r.execucoes.length})</h2>
    ${r.execucoes.length ? `<table><tr><th>início</th><th>status</th><th>resumo</th></tr>${r.execucoes.map(x => `<tr><td>${dataHora(x.inicio)}</td><td>${pill(x.status)}</td><td>${esc(x.resumo)}</td></tr>`).join("")}</table>` : `<div class="vazio">Nenhuma.</div>`}`;
}
const contarFalhas = semEmpilhar('rodape', async function(){
  try {
    const [r, mt] = await Promise.all([api("/api/falhas"), api("/api/metricas")]);
    if (!S.saude) S.saude = await api("/api/saude");
    $("#nfalhas").textContent = r.resumo_atual?.videos_com_falha || "";
    const ruins = (mt.conferencia||[]).filter(c => !c.ok), sd = S.saude;
    $("#statusServidor").innerHTML = `<div>${sd.ok ? '<span class="s-ok">● programa pronto</span>' : `<span class="s-falha" data-dica="${esc(`ffmpeg: ${sd.ffmpeg||'NÃO ACHADO'} | ffprobe: ${sd.ffprobe||'NÃO ACHADO'} | yt-dlp: ${sd.yt_dlp||'NÃO ACHADO'} | modelo ${sd.modelo_whisper}: ${sd.modelo_baixado?'ok':'NÃO BAIXADO'}`)}">● falta algo no programa</span>`}</div>
      <div>${ruins.length ? `<span class="s-falha" data-dica="${esc(ruins.map(c=>`${c.nome}: ${c.valor} ≠ ${c.esperado}`).join(' | '))}">✗ ${ruins.length} número(s) não batem</span>` : `<span class="s-ok" data-dica="${esc((mt.conferencia||[]).map(c=>c.nome).join(' · '))}">✓ números conferidos</span>`}</div>`;
  } catch (e) {
    let antigo = false; try { antigo = (await fetch('/api/saude')).status === 404; } catch {}
    $("#statusServidor").innerHTML = antigo ? '<span class="s-falha" data-dica="A página é nova mas o servidor que está respondendo é antigo. Feche todas as janelas pretas do painel e abra o ABRIR_PAINEL.bat.">● servidor ANTIGO rodando — reabra o painel</span>'
                                            : '<span class="s-falha">● servidor desligado</span>';
  }
});

// ------------------------------------------------------------- BANCO
async function vBanco(nome = "videos", pagina = 0, busca = ""){
  const r = await api(`/api/tabela?nome=${nome}&pagina=${pagina}&q=${encodeURIComponent(busca)}`);
  $("#principal").innerHTML = `<h1>Banco de dados</h1><p class="sub">Arquivo <code>dados/cv.db</code>. Leitura direta das tabelas, sem filtro nem resumo.</p>
    <div class="chips" style="margin-bottom:10px">${Object.entries(r.contagens).map(([t,n]) => `<span class="chip ${t===nome?"sel":""}" onclick="vBanco('${t}')">${t} (${n})</span>`).join("")}</div>
    <div class="barra"><input id="busca" placeholder="buscar em ${nome}…" value="${esc(busca)}" style="width:320px"><button onclick="vBanco('${nome}',0,$('#busca').value)">Buscar</button>
      <span class="sub">${r.total} linha(s) · página ${pagina+1}</span>
      ${pagina>0?`<button onclick="vBanco('${nome}',${pagina-1},'${esc(busca)}')">←</button>`:""}${(pagina+1)*100<r.total?`<button onclick="vBanco('${nome}',${pagina+1},'${esc(busca)}')">→</button>`:""}</div>
    <div class="tab-wrap"><table><tr>${r.colunas.map(c => `<th>${esc(c)}</th>`).join("")}</tr>
      ${r.linhas.map(l => `<tr>${r.colunas.map(c => `<td title="${esc(l[c])}">${esc(l[c])}</td>`).join("")}</tr>`).join("")}</table></div>`;
  $("#busca").onkeydown = e => { if (e.key === "Enter") vBanco(nome, 0, e.target.value); };
}

// ------------------------------------------------------------- início
contarFalhas(); setInterval(contarFalhas, 12000);
setInterval(async () => { if (S.view === "videos") return; try { const d = await api("/api/painel"); $("#nproc").textContent = d.vivo ? (d.fila.filter(v => v.status === "rodando").length || "•") : ""; } catch {} }, 4000);
function progressoGlobal(d){
  const p=d.progresso_lote;if(!p||!d.vivo)return '';
  const ativo=d.fila.find(v=>v.status==='rodando'),t=ativo?.progresso||{};
  const pct=t.total_s?Math.min(99,Math.round(100*(t.ate_s||0)/t.total_s)):null;
  const falhas=d.fila.filter(v=>v.status==='falha').length;
  return `<section class="progresso-lote"><div class="progresso-cab"><b>${d.vivo?'Preparação em andamento':p.preparados===p.aceitos&&p.aceitos?'Preparação encerrada':'Estado da preparação'}</b><strong>${p.pct_preparacao}%</strong></div><progress value="${p.pct_preparacao}" max="100" aria-label="Preparação técnica do lote">${p.pct_preparacao}%</progress><p>${esc(d.escopo||'')} · ${p.preparados} de ${p.aceitos} preparados · ${p.encerrados} passaram pelo processamento atual · ${p.a_iniciar} ainda não iniciados${falhas?' · '+falhas+' com falha aberta':''}</p>${ativo?`<div class="progresso-atual"><b>${esc(ativo.titulo)}</b> · ${esc(NOME[ativo.atual]||'Processando')}${pct!==null?`<progress value="${pct}" max="100" aria-label="Trecho de áudio alcançado">${pct}%</progress><span>Áudio alcançado: ${fmt(t.ate_s)} de ${fmt(t.total_s)} (${pct}%). O tempo de execução pode variar.</span>`:'<span>Aguardando o próximo registro da etapa; sem estimativa de tempo.</span>'}</div>`:''}<p class="sub">100% aqui significa preparação pelo programa. Interpretação e revisão são etapas separadas.</p>${d.pacotes_invalidos?`<p class="s-alerta">${d.pacotes_invalidos} pacotes antigos bloqueados até a preparação ser corrigida. Eles não contam como prontos para IA.</p>`:''}</section>`;
}
function controleFila(d){if(!d.espera)return d.fila_pausada?`<div class="fila-inativa"><span>Fila automática pausada</span><button onclick="agirFila('retomar')">Retomar</button></div>`:'';return `<section class="controle-fila"><div><b>${d.espera} lote(s) na fila</b> · ${d.fila_pausada?'Pausada':'Automática após o lote ativo'} <button onclick="agirFila('${d.fila_pausada?'retomar':'pausar'}')">${d.fila_pausada?'Retomar fila':'Pausar fila'}</button><button onclick="localStorage.removeItem('aviso-ia-oculto');atualizarVideos()">Mostrar aviso da IA (${d.aguardando_ia})</button></div>${(d.fila_espera||[]).map((l,i)=>`<div class="item-fila">${i+1}. ${(l.links||[]).length+(l.arquivos||[]).length} entradas · ${dataCurta(l.pedido_em)} <button onclick="agirFila('cancelar','${esc(l.id)}')">Cancelar este lote</button></div>`).join('')}<small>Pedidos repetidos são ignorados. Cancelamentos ficam preservados no histórico da fila. <a href="/midia?p=dados%2Ffila_historico.jsonl" target="_blank">Abrir histórico</a></small></section>`;}
async function agirFila(acao,id){try{const r=await api('/api/fila',{acao,id});if(r.erro)throw Error(r.erro);await atualizarVideos();}catch(e){alertaTopo(esc(e.message));}}
function rotear(){ const [v, arg] = (location.hash.slice(1) || "workflow").split("/"); if (S._rot === location.hash) return; S._rot = location.hash; ir(v, arg ? decodeURIComponent(arg) : undefined); }
window.addEventListener("hashchange", rotear); rotear();

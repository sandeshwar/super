let state = { view: "tree", tasks: [], gates: {}, criticals: [], selected: null };

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function refresh() {
  const [tree, ledger] = await Promise.all([
    api("/api/tree"), api("/api/ledger"),
  ]);
  state.tasks = tree.tasks;
  state.gates = ledger.gates;
  state.criticals = ledger.open_criticals;
  if (!state.selected && state.tasks.length) state.selected = state.tasks[0].id;
  const m = document.getElementById("model");
  if (m) {
    // fetch model via health if available
    try { const h = await api("/api/health"); if (h.model) m.textContent = (h.model.split("/").pop()||h.model); } catch {}
  }
  render();
}

function badge(s) { return `<span class="badge ${s}">${s}</span>`; }
function esc(s) { return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

function treeView() {
  const items = state.tasks.map(t =>
    `<button data-id="${t.id}" style="display:flex;align-items:center;gap:10;width:100%;text-align:left;padding:11px 12px;border-radius:10px;border:1px solid ${state.selected===t.id?'var(--accent-border)':'var(--border-subtle)'};background:${state.selected===t.id?'var(--accent-soft)':'var(--bg-2)'};margin-bottom:6px;cursor:pointer">
      <span class="mono" style="min-width:28px;height:22px;display:grid;place-items:center;border-radius:7px;background:${state.selected===t.id?'var(--accent)':'var(--bg-3)'};color:${state.selected===t.id?'var(--accent-fg)':'var(--fg-2)'};font-size:11px;font-weight:700">${esc(t.id)}</span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:${state.selected===t.id?600:500};color:${state.selected===t.id?'var(--fg-0)':'var(--fg-1)'}">${esc(t.title)}</span>
      ${badge(t.status)}
    </button>`
  ).join("") || `<div class="card" style="text-align:center;padding:28px;color:var(--fg-2)"><div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;font-weight:700;margin-bottom:6px">No tasks yet</div><code>python3 -m super.cli task-add "Title" --done "check"</code></div>`;
  const sel = state.tasks.find(t => t.id === state.selected) || state.tasks[0];
  const detail = sel ? `<div class="card" style="display:flex;flex-direction:column;gap:12">
    <div><div class="mono" style="font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--fg-3);font-weight:700;margin-bottom:4px">TASK ${esc(sel.id)}</div>
    <h3 style="font-size:18px;font-weight:700;letter-spacing:-.02em">${esc(sel.title)}</h3>
    <div style="display:flex;gap:6;margin-top:8;flex-wrap:wrap"><span class="badge">${esc(sel.status)}</span><span class="mono" style="font-size:11px;padding:4px 8px;border-radius:999px;background:var(--bg-3);border:1px solid var(--border);color:var(--fg-2)">needs: ${esc((sel.needs||[]).join(", ")||"nothing")}</span></div></div>
    <div style="padding:11px 12px;border-radius:10px;background:var(--bg-1);border:1px solid var(--border-subtle)"><div style="font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--fg-3);margin-bottom:4px">WHY</div><div style="font-size:13px;color:var(--fg-1);line-height:1.6">${esc(sel.why||"—")}</div></div>
    <div style="padding:11px 12px;border-radius:10px;background:var(--bg-1);border:1px solid var(--border-subtle)"><div style="font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--fg-3);margin-bottom:4px">DONE LOOKS LIKE</div><div style="font-size:13px;color:var(--fg-1);line-height:1.6">${esc(sel.done||"—")}</div></div>
    <div style="padding:11px 12px;border-radius:10px;background:${sel.proof?'var(--green-bg)':'var(--bg-1)'};border:1px solid ${sel.proof?'var(--green-border)':'var(--border-subtle)'}"><div style="font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--fg-3);margin-bottom:4px">PROOF</div><div style="font-size:12px;color:${sel.proof?'var(--fg-1)':'var(--fg-3)'};font-family:var(--font-mono);font-style:${sel.proof?'normal':'italic'}">${esc(sel.proof||"(empty — not done)")}</div></div>
  </div>` : `<div class="card" style="text-align:center;padding:24px;color:var(--fg-3)">Select a task</div>`;
  return `<div class="cols"><div style="overflow:auto">${items}</div><div style="overflow:auto">${detail}</div></div>`;
}

function approveView() {
  const cand = state.tasks.find(t => t.status === "waiting") || state.tasks.find(t => t.status === "doing");
  if (!cand) return `<div class="card" style="text-align:center;padding:40px;color:var(--fg-2)"><div style="width:48px;height:48px;border-radius:12px;background:var(--green-bg);border:1px solid var(--green-border);display:grid;place-items:center;margin:0 auto 12px;color:var(--green)">✓</div><div style="font-weight:700;color:var(--fg-0)">Queue clear</div><div class="small muted" style="margin-top:6px">All proven or empty — provenance intact.</div></div>`;
  const gp = Object.values(state.gates).reduce((s,g)=>s+g.pass,0);
  const gr = Object.values(state.gates).reduce((s,g)=>s+g.reject,0);
  return `<div style="display:grid;grid-template-columns:1.15fr .85fr;gap:16">
    <div class="card" style="display:flex;flex-direction:column;gap:14">
      <div><div class="mono" style="font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--fg-3);font-weight:700">Awaiting review</div><h3 style="font-size:18px;font-weight:700;margin-top:2">[${esc(cand.id)}] ${esc(cand.title)}</h3></div>
      <div style="padding:11px 12px;border-radius:10px;background:var(--bg-1);border:1px solid var(--border-subtle)"><div style="font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--fg-3);margin-bottom:4px">DONE LOOKS LIKE</div><div style="font-size:13px;color:var(--fg-1)">${esc(cand.done||"-")}</div></div>
      <div style="padding:11px 12px;border-radius:10px;background:var(--bg-1);border:1px solid var(--border-subtle)"><div style="font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--fg-3);margin-bottom:4px">NEEDS</div><div style="font-size:13px;color:var(--fg-1)">${esc((cand.needs||[]).join(", ")||"nothing")}</div></div>
      <div style="border:1px solid var(--border);border-radius:10px;overflow:hidden;background:var(--bg-1)"><div style="padding:10px 12px;border-bottom:1px solid var(--border-subtle);display:flex;justify-content:space-between"><span style="font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--fg-3)">CRITIC EVIDENCE</span><span class="mono" style="font-size:11px;color:${gr?'var(--yellow)':'var(--green)'}">${gp} pass · ${gr} reject</span></div><div style="padding:12px"><div style="height:6px;border-radius:999px;background:var(--bg-3);overflow:hidden;display:flex"><i style="flex:${gp||0.01};background:var(--green)"></i><i style="flex:${gr||0.01};background:var(--yellow)"></i></div><div style="margin-top:10px;padding:10px 12px;border-radius:8px;background:${gr?'var(--yellow-bg)':'var(--green-bg)'};border:1px solid ${gr?'var(--yellow-border)':'var(--green-border)'};color:${gr?'var(--yellow)':'var(--green)'};font-size:13px">${gr?`<strong>${gr} rejection${gr!==1?'s':''}</strong> — review before approving.`:`All <strong>${gp} checks passed</strong> — approve only on linked proof.`}</div></div></div>
    </div>
    <div style="display:flex;flex-direction:column;gap:12">
      <div class="card" style="padding:0;overflow:hidden"><div style="padding:12px 14px;border-bottom:1px solid var(--border-subtle);display:flex;justify-content:space-between;align-items:center"><span style="font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--fg-3)">QUEUE</span><span class="badge" style="background:var(--accent-soft);color:var(--accent);border-color:var(--accent-border)">${state.tasks.filter(t=>t.status==="waiting"||t.status==="doing").length} pending</span></div><div>${state.tasks.filter(t=>t.status==="waiting"||t.status==="doing").map(t=>`<div style="padding:10px 14px;border-bottom:1px solid var(--border-subtle);display:flex;justify-content:space-between;align-items:center;font-size:13px"><span>[${esc(t.id)}] ${esc(t.title)}</span>${badge(t.status)}</div>`).join("")}</div></div>
      <div class="card" style="display:flex;flex-direction:column;gap:12"><div style="font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--fg-3)">DECISION</div><input id="note" type="text" placeholder="proof link or note, e.g. tests/login.py green"><div class="row" style="margin:0"><button class="primary" id="ok" style="flex:1">Approve</button><button id="back" style="flex:1">Send back to fix</button></div></div>
    </div>
  </div>`;
}

function reportView() {
  const rows = state.tasks.map(t =>
    `<tr><td class="mono" style="font-weight:600">${esc(t.id)}</td><td style="font-weight:550;color:var(--fg-0)">${esc(t.title)}</td><td>${badge(t.status)}</td><td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:var(--font-mono);font-size:12px">${esc(t.proof||"—")}</td></tr>`
  ).join("");
  const proven = state.tasks.filter(t => t.status === "proven").length;
  const total = state.tasks.length;
  const pct = total?Math.round(proven/total*100):0;
  const gp = Object.values(state.gates).reduce((s,g)=>s+g.pass,0);
  const gr = Object.values(state.gates).reduce((s,g)=>s+g.reject,0);
  return `<div style="display:flex;flex-direction:column;gap:14">
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12">
      ${[{l:"PROVEN",v:`${proven}/${total||"—"}`,c:pct===100?"var(--green)":"var(--fg-0)"},{l:"COMPLETE",v:`${pct}%`,c:pct===100?"var(--green)":"var(--fg-0)"},{l:"GATES PASS",v:String(gp),c:"var(--green)"},{l:"REJECT",v:String(gr),c:gr?"var(--red)":"var(--fg-0)"}].map(s=>`<div class="card" style="text-align:center;padding:16px"><div style="font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--fg-3);margin-bottom:4px">${s.l}</div><div style="font-size:26px;font-weight:800;color:${s.c};letter-spacing:-.02em">${s.v}</div></div>`).join("")}
    </div>
    <div style="display:grid;grid-template-columns:1.2fr .8fr;gap:12">
      <div class="card" style="display:flex;gap:14;align-items:center"><div style="width:84px;height:84px;border-radius:999px;background:var(--bg-1);border:2px solid ${pct===100?'var(--green)':'var(--accent)'};display:grid;place-items:center;padding:6px"><div style="width:100%;height:100%;border-radius:999px;background:var(--bg-2);display:grid;place-items:center;border:1px solid var(--border)"><div style="text-align:center"><div style="font-size:18px;font-weight:800;color:${pct===100?'var(--green)':'var(--fg-0)'}">${pct}<span style="font-size:11px;color:var(--fg-3)">%</span></div><div class="mono" style="font-size:10px;color:var(--fg-3)">proven</div></div></div></div><div style="flex:1"><div style="display:flex;justify-content:space-between;font-size:11px;color:var(--fg-3);margin-bottom:6px"><span class="mono">Progress</span><span class="mono">${proven}/${total}</span></div><div style="height:8px;border-radius:999px;background:var(--bg-4);overflow:hidden"><i style="display:block;height:100%;width:${pct}%;background:var(--accent);border-radius:999px"></i></div></div></div>
      <div class="card"><div style="font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--fg-3);margin-bottom:8px">GATE BREAKDOWN</div><div style="display:flex;flex-direction:column;gap:8">${Object.entries(state.gates).map(([k,s])=>`<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 10px;border-radius:8px;background:var(--bg-1);border:1px solid var(--border-subtle)"><span class="mono" style="font-size:12px;color:var(--fg-1)">${esc(k)}</span><span class="mono" style="font-size:11px"><span style="color:var(--green)">${s.pass}</span> <span style="color:var(--fg-3)">/</span> <span style="color:${s.reject?'var(--red)':'var(--fg-3)'}">${s.reject}</span></span></div>`).join("")||`<div class="small muted">No gate events yet</div>`}</div></div>
    </div>
    <div class="card" style="padding:0;overflow:hidden"><div style="padding:12px 14px;border-bottom:1px solid var(--border-subtle);font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--fg-3)">TASKS</div><table><thead><tr><th style="width:50px">ID</th><th>TASK</th><th>STATUS</th><th>PROOF</th></tr></thead><tbody>${rows||`<tr><td colspan=4 style="text-align:center;padding:24px;color:var(--fg-3)">No tasks</td></tr>`}</tbody></table></div>
    ${state.criticals.length?`<div class="card" style="border-color:var(--red-border)"><div style="font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--red);margin-bottom:8px">OPEN CRITICALS (${state.criticals.length})</div>${state.criticals.map((c:any)=>`<div style="padding:8px 12px;background:var(--red-bg);border:1px solid var(--red-border);border-radius:8px;margin-bottom:6px;font-size:13px;color:var(--red)">${esc(c.text||c.layer||JSON.stringify(c))}</div>`).join("")}</div>`:""}
  </div>`;
}

function render() {
  document.querySelectorAll("nav button").forEach(b =>
    b.classList.toggle("active", b.dataset.view === state.view));
  const v = document.getElementById("view");
  v.innerHTML = state.view === "tree" ? treeView() : state.view === "approve" ? approveView() : state.view === "chat" ? chatView() : reportView();
  const proven = state.tasks.filter(t => t.status === "proven").length;
  document.getElementById("bar").innerHTML =
    `<span class="mono" style="display:inline-flex;gap:8;align-items:center"><span style="width:6px;height:6px;border-radius:999px;background:var(--green);display:inline-block"></span>${proven}/${state.tasks.length} proven · gates ${esc(JSON.stringify(state.gates))} · criticals ${state.criticals.length}</span><span style="margin-left:auto" class="mono">SUPER v1.0</span>`;
  v.querySelectorAll("[data-id]").forEach(a => a.onclick = e => {
    e.preventDefault(); state.selected = a.dataset.id; render();
  });
  const ok = document.getElementById("ok");
  if (ok) ok.onclick = async () => {
    const cand = state.tasks.find(t => t.status === "waiting") || state.tasks.find(t => t.status === "doing");
    const note = document.getElementById("note").value || "approved in dashboard";
    await api("/api/approve", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: cand.id, note }) });
    await refresh();
  };
  const back = document.getElementById("back");
  if (back) back.onclick = async () => {
    const cand = state.tasks.find(t => t.status === "waiting") || state.tasks.find(t => t.status === "doing");
    const note = document.getElementById("note").value || "needs work";
    await api("/api/send-back", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: cand.id, note }) });
    await refresh();
  };
  // chat wiring
  const sendBtn = document.getElementById("chat-send");
  const chatInput = document.getElementById("chat-input");
  const chatNew = document.getElementById("chat-new");
  if (sendBtn) sendBtn.onclick = () => sendChat();
  if (chatInput) chatInput.onkeydown = e => { if (e.key==="Enter"&&!e.shiftKey){ e.preventDefault(); sendChat(); } };
  if (chatNew) chatNew.onclick = async () => { const r=await api("/api/sessions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title:"New chat"})}); state.chatId=r.id; render(); loadChat(); };
  if (state.view==="chat") loadChat();
}

let chatState = { sid: null, msgs: [], busy:false };
async function loadChat(){
  try{
    const {sessions} = await api("/api/sessions");
    if (!chatState.sid && sessions.length) chatState.sid = sessions[0].id;
    if (chatState.sid){
      const s = await api(`/api/session?id=${chatState.sid}`);
      chatState.msgs = s.messages;
      const box = document.getElementById("chat-msgs");
      if (box) { box.scrollTop = box.scrollHeight; }
    }
  }catch{}
  if (state.view==="chat") renderChatMsgs();
}
function renderChatMsgs(){
  const box = document.getElementById("chat-msgs");
  if (!box) return;
  box.innerHTML = chatState.msgs.map(m=>`<div class="msg ${m.role}">${esc(m.content)}${m.gate?`<span class="gate ${m.gate.ok?'grounded':'unverified'}">${m.gate.ok?'grounded':('unverified: '+(m.gate.missing||[]).join(", "))}</span>`:""}</div>`).join("") + (chatState.busy?`<div class="msg assistant" style="opacity:.6">thinking…</div>`:"");
  box.scrollTop = box.scrollHeight;
}
async function sendChat(){
  const inp = document.getElementById("chat-input");
  const txt = inp.value.trim();
  if (!txt||chatState.busy) return;
  chatState.busy=true; chatState.msgs.push({role:"user",content:txt}); chatState.msgs.push({role:"assistant",content:""}); inp.value=""; renderChatMsgs();
  try{
    const r = await fetch("/api/chat/stream",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({session_id:chatState.sid,message:txt})});
    if (!r.ok) throw new Error(await r.text());
    const reader = r.body.getReader(); const dec=new TextDecoder(); let buf=""; let acc="";
    for(;;){
      const {value,done:eof}=await reader.read();
      if(value) buf+=dec.decode(value,{stream:true});
      let idx; while((idx=buf.indexOf("\n\n"))>=0){ const frame=buf.slice(0,idx); buf=buf.slice(idx+2); for(const line of frame.split("\n")){ if(!line.startsWith("data:")) continue; const evt=JSON.parse(line.slice(5).trim()); if(evt.delta){ acc+=evt.delta; chatState.msgs[chatState.msgs.length-1].content=acc; renderChatMsgs(); } if(evt.done){ chatState.sid=evt.session_id; chatState.msgs[chatState.msgs.length-1].gate=evt.gate; } } }
      if(eof) break; if(acc && buf.length===0 && chatState.msgs[chatState.msgs.length-1].gate) break;
    }
  }catch(e){ chatState.msgs.pop(); const err=document.getElementById("chat-err"); if(err){ err.textContent=e.message; err.style.display="block"; } }
  chatState.busy=false; renderChatMsgs();
}

function chatView(){
  return `<div class="chat-wrap">
    <div class="sessions">
      <button id="chat-new" class="primary" style="width:100%;margin-bottom:8px">+ New Chat</button>
      <div id="chat-sessions" class="small muted" style="text-align:center;padding:12px">Select or start a chat</div>
    </div>
    <div class="chat">
      <div id="chat-msgs" class="msgs"><div class="msg assistant">Start a conversation — the model sees your task context automatically. Backticked <code>symbols</code> are ground-checked.</div></div>
      <div id="chat-err" class="err" style="display:none;margin:8px"></div>
      <div class="composer"><input id="chat-input" type="text" placeholder="Ask about the repo…"><button id="chat-send" class="primary">Send</button></div>
    </div>
  </div>`;
}

document.querySelectorAll("nav button").forEach(b => b.onclick = () => { state.view = b.dataset.view; render(); });
refresh().catch(e => document.getElementById("view").innerHTML = `<div class="card" style="border-color:var(--red-border);background:var(--red-bg);color:var(--red)">Server error: ${esc(e.message)}</div>`);
setInterval(refresh, 5000);

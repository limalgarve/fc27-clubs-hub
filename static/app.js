
let currentClub=null, clubData=null;
const $=s=>document.querySelector(s), $$=s=>document.querySelectorAll(s);
function toast(t){let x=$("#toast");x.textContent=t;x.style.display="block";setTimeout(()=>x.style.display="none",3500)}
function fmt(n,d=0){if(n===null||n===undefined||n==="")return "—";return Number(n).toLocaleString("pt-BR",{maximumFractionDigits:d})}
function dateBR(s){if(!s)return "";let d=new Date(s.replace(" ","T"));return isNaN(d)?s:d.toLocaleString("pt-BR",{day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit"})}
function typeLabel(t){return {leagueMatch:"Liga",friendlyMatch:"Amistoso",playoffMatch:"Playoff"}[t]||t}
function resultLabel(r){return r==="win"?"VITÓRIA":r==="draw"?"EMPATE":"DERROTA"}
function resultClass(r){return r==="win"?"win":r==="draw"?"draw":"loss"}
async function api(url,opt){let r=await fetch(url,opt);let j;try{j=await r.json()}catch{j={detail:"Resposta inválida"}}if(!r.ok)throw Error(j.detail||"Erro");return j}
async function loadClubs(){
 let clubs=await api("/api/clubs"); let box=$("#clubList");box.innerHTML="";
 clubs.forEach(c=>{let d=document.createElement("div");d.className="clubitem"+(currentClub===c.club_id?" active":"");d.innerHTML=`<b>${c.name}</b><small>${c.total_matches||0} partidas • ID ${c.club_id}</small>`;d.onclick=()=>openClub(c.club_id);box.appendChild(d)})
}
async function doUpdate(){
 let q=$("#clubInput").value.trim();if(!q)return toast("Digite o nome do clube.");
 $("#updateBtn").disabled=true;$("#updateBtn").textContent="ATUALIZANDO...";
 try{
 let token=localStorage.getItem("fc27_admin_token")||"";
 let headers={};
 if(token)headers["X-Admin-Token"]=token;
 let r;
 try{r=await api("/api/update?q="+encodeURIComponent(q),{method:"POST",headers})}
 catch(e){
   if(e.message.includes("Senha de atualização necessária")||e.message.includes("Senha de atualização incorreta")){
     let pwd=prompt("Digite a senha para atualizar os dados do clube:");
     if(!pwd)throw e;
     localStorage.setItem("fc27_admin_token",pwd);
     r=await api("/api/update?q="+encodeURIComponent(q),{method:"POST",headers:{"X-Admin-Token":pwd}});
   }else throw e;
 }
 toast(`${r.name}: ${r.new_matches} nova(s) partida(s). Total ${r.total_matches}.`);await loadClubs();await openClub(r.club_id)}
 catch(e){toast("Erro: "+e.message)}finally{$("#updateBtn").disabled=false;$("#updateBtn").textContent="ATUALIZAR CLUBE"}
}
async function openClub(id){
 currentClub=String(id);clubData=await api(`/api/club/${id}?limit=20`);$("#empty").classList.add("hidden");$("#content").classList.remove("hidden");
 let c=clubData.club;$("#clubName").textContent=c.name;$("#clubMeta").textContent=`ID ${c.club_id} • ${c.stadium||"Estádio não informado"} • Atualizado ${dateBR(c.updated_at)}`;
 let gp=Number(c.games_played||0), wr=gp?Number(c.wins||0)/gp*100:0;
 let ks=[["Skill Rating",fmt(c.skill_rating)],["Jogos",fmt(c.games_played)],["Vitórias",fmt(c.wins)],["Aproveitamento",fmt(wr,1)+"%"],["Gols",fmt(c.goals)],["Melhor Divisão",fmt(c.best_division)]];
 $("#kpis").innerHTML=ks.map(x=>`<div class="kpi"><span>${x[0]}</span><b>${x[1]}</b></div>`).join("");
 renderDashboard();renderPlayers();await loadMatches();await loadRankings();await loadClubs();
}
function renderDashboard(){
 let m=clubData.matches.slice(0,10);$("#form").innerHTML=`<div class="formrow">${m.map(x=>`<div class="dot ${resultClass(x.result)}">${x.result==="win"?"V":x.result==="draw"?"E":"D"}</div>`).join("")}</div>`;
 let p=[...clubData.members].sort((a,b)=>(b.goals||0)-(a.goals||0)).slice(0,5);
 $("#topPlayers").innerHTML=p.map((x,i)=>`<div class="rankrow"><b>${i+1}</b><span class="playerlink" onclick="openPlayer('${encodeURIComponent(x.name)}')">${x.name}</span><span>⚽ ${fmt(x.goals)}</span><span>🎯 ${fmt(x.assists)}</span><span>★ ${fmt(x.average_rating,1)}</span></div>`).join("");
 $("#recentMatches").innerHTML=m.slice(0,6).map(matchCard).join("");
}
function renderPlayers(){
 $("#playersBody").innerHTML=clubData.members.map(x=>`<tr><td class="playerlink" onclick="openPlayer('${encodeURIComponent(x.name)}')">${x.name}</td><td>${x.position||"—"}</td><td>${fmt(x.overall)}</td><td>${fmt(x.games_played)}</td><td>${fmt(x.goals)}</td><td>${fmt(x.assists)}</td><td>${fmt(x.average_rating,1)}</td><td>${fmt(x.pass_success_rate,1)}%</td><td>${fmt(x.tackle_success_rate,1)}%</td></tr>`).join("");
}
function matchCard(x){return `<div class="matchcard"><div class="matchhead" onclick="toggleMatch('${x.match_id}',this)">
<div><b>${typeLabel(x.match_type)}</b><div class="muted">${dateBR(x.timestamp)}</div></div>
<div class="score">${x.club_name||clubData.club.name} &nbsp; ${x.goals} × ${x.goals_against} &nbsp; ${x.opponent_name}<span class="badge ${resultClass(x.result)}">${resultLabel(x.result)}</span></div>
<div class="opp"><span class="muted">${x.dnf?"DNF":""}</span></div></div><div class="players-detail hidden"></div></div>`}
async function toggleMatch(mid,el){let box=el.nextElementSibling;if(!box.classList.contains("hidden")){box.classList.add("hidden");return}
 let d=await api(`/api/club/${currentClub}/match/${mid}`);box.innerHTML=`<div class="tablewrap"><table><thead><tr><th>Jogador</th><th>Pos.</th><th>Nota</th><th>Gols</th><th>AST</th><th>Chutes</th><th>Passes</th><th>Desarmes</th><th>Defesas</th><th>MOTM</th></tr></thead><tbody>${d.players.map(p=>`<tr><td class="playerlink" onclick="openPlayer('${encodeURIComponent(p.name)}')">${p.name}</td><td>${p.position||"—"}</td><td>${fmt(p.rating,1)}</td><td>${fmt(p.goals)}</td><td>${fmt(p.assists)}</td><td>${fmt(p.shots)}</td><td>${fmt(p.passes_made)}/${fmt(p.pass_attempts)}</td><td>${fmt(p.tackles_made)}/${fmt(p.tackle_attempts)}</td><td>${fmt(p.saves)}</td><td>${p.motm?"★":"—"}</td></tr>`).join("")}</tbody></table></div>`;box.classList.remove("hidden")}
async function loadMatches(){if(!currentClub)return;let lim=$("#matchLimit").value,typ=$("#matchType").value;let a=await api(`/api/club/${currentClub}/matches?limit=${lim}&match_type=${typ}`);$("#matchesList").innerHTML=a.length?a.map(matchCard).join(""):`<div class="panel">Nenhuma partida armazenada.</div>`}
async function loadRankings(){if(!currentClub)return;let last=$("#rankingLast").value;let a=await api(`/api/club/${currentClub}/rankings?last=${last}`);$("#rankBody").innerHTML=a.map((x,i)=>`<tr><td>${i+1}</td><td class="playerlink" onclick="openPlayer('${encodeURIComponent(x.name)}')">${x.name}</td><td>${fmt(x.games)}</td><td>${fmt(x.goals)}</td><td>${fmt(x.assists)}</td><td>${fmt(x.average_rating,2)}</td><td>${fmt(x.motm)}</td></tr>`).join("")}
async function openPlayer(enc){let name=decodeURIComponent(enc);let a=await api(`/api/club/${currentClub}/player/${encodeURIComponent(name)}`);let games=a.length,goals=a.reduce((s,x)=>s+(x.goals||0),0),ast=a.reduce((s,x)=>s+(x.assists||0),0),avg=a.reduce((s,x)=>s+(x.rating||0),0)/games;
 $("#modalContent").innerHTML=`<span class="eyebrow">JOGADOR</span><h1>${name}</h1><div class="kpis"><div class="kpi"><span>Jogos</span><b>${games}</b></div><div class="kpi"><span>Gols</span><b>${goals}</b></div><div class="kpi"><span>Assistências</span><b>${ast}</b></div><div class="kpi"><span>Nota média</span><b>${fmt(avg,2)}</b></div></div><div class="panel"><div class="panel-title">PARTIDAS RECENTES</div><div class="tablewrap"><table><thead><tr><th>Data</th><th>Adversário</th><th>Nota</th><th>Gols</th><th>AST</th><th>Resultado</th></tr></thead><tbody>${a.slice(0,30).map(x=>`<tr><td>${dateBR(x.timestamp)}</td><td>${x.opponent_name}</td><td>${fmt(x.rating,1)}</td><td>${fmt(x.goals)}</td><td>${fmt(x.assists)}</td><td>${resultLabel(x.result)}</td></tr>`).join("")}</tbody></table></div></div>`;$("#modal").classList.remove("hidden")}
function closeModal(){$("#modal").classList.add("hidden")}
$$(".tabs button").forEach(b=>b.onclick=()=>{$$(".tabs button").forEach(x=>x.classList.remove("active"));$$(".tab").forEach(x=>x.classList.remove("active"));b.classList.add("active");$("#"+b.dataset.tab).classList.add("active")});
$("#updateBtn").onclick=doUpdate;$("#refreshBtn").onclick=()=>{$("#clubInput").value=clubData.club.name;doUpdate()};$("#exportBtn").onclick=()=>location.href=`/api/club/${currentClub}/export.xlsx`;
$("#matchLimit").onchange=loadMatches;$("#matchType").onchange=loadMatches;$("#rankingLast").onchange=loadRankings;$("#clubInput").onkeydown=e=>{if(e.key==="Enter")doUpdate()};
loadClubs();

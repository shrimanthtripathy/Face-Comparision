const $=s=>document.querySelector(s), esc=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const files={}; let R=null, mode="a"; const off=new Set();
function bind(id,key,drop){const inp=$(id),box=$(drop);
  const set=f=>{if(!f)return;files[key]=f;let im=box.querySelector("img")||box.appendChild(document.createElement("img"));im.src=URL.createObjectURL(f);im.alt=f.name;ready()};
  inp.onchange=()=>set(inp.files[0]);
  box.ondragover=e=>{e.preventDefault();box.classList.add("over")};box.ondragleave=()=>box.classList.remove("over");
  box.ondrop=e=>{e.preventDefault();box.classList.remove("over");set(e.dataTransfer.files[0])}}
bind("#fa","a","#dropA");bind("#fb","b","#dropB");
const ready=()=>$("#run").disabled=!(files.a&&files.b&&$("#consent").checked);$("#consent").onchange=ready;
const msg=(t,e)=>{$("#msg").textContent=t;$("#msg").className=e?"err":""};

$("#run").onclick=async()=>{
  const fd=new FormData();fd.append("a",files.a);fd.append("b",files.b);fd.append("consent","true");
  fd.append("case_ref",$("#ref").value);fd.append("examiner",$("#exa").value);fd.append("purpose",$("#pur").value);fd.append("age_gap",$("#gap").value);
  $("#run").disabled=true;msg("Analysing: detecting landmarks, aligning faces, comparing...");
  try{const r=await fetch($("#isgroup").checked?"/api/group/scan":"/api/compare",{method:"POST",body:fd});const j=await r.json();
    if(r.status===401){needAuth();return}if(!r.ok)throw new Error(typeof j.detail==="string"?j.detail:"The comparison failed. Check the images and try again.");
    if($("#isgroup").checked){SCAN=j;renderScan()}else{R=j;render()}msg("")}catch(e){msg(e.message,true)}finally{ready()}};

function render(){
  $("#intake").classList.add("hidden");$("#scan").classList.add("hidden");$("#results").classList.remove("hidden");
  const c=R.conclusion,g=R.geometry,e=R.embedding;
  $("#label").textContent=c.label;
  $("#rail").innerHTML=[0,1,2,3,4].map(i=>`<i class="${i===c.level?"on":""}"></i>`).join("");
  $("#flags").innerHTML=c.flags.map(f=>`<li>${esc(f)}</li>`).join("");
  $("#rationale").textContent=c.rationale.join(" ")+(R.group?" Group photo: face "+R.group.face_number+" of "+R.group.faces_searched+" selected (rank "+R.group.rank+" by similarity).":"");
  $("#cos").textContent=e.cosine==null?"n/a":e.cosine.toFixed(3);
  $("#agr").textContent=g.agreement_index+" / 100";$("#mpd").textContent=g.mean_ratio_diff_pct+" %";const ag=R.age||{};$("#ages").textContent=(ag.estimated_a??"n/a")+" / "+(ag.estimated_b??"n/a")+(ag.gap!=null?" (gap "+Math.round(ag.gap)+" y)":"");
  $("#pts").textContent=R.landmarks.count+" landmarks per face, aligned by Procrustes analysis. "+(e.available?e.model:"Face-recognition model unavailable, so no identity score was produced.");
  const qa=R.quality.a,qb=R.quality.b,row=(n,a,b)=>`<tr><td>${n}</td><td>${a}</td><td>${b}</td></tr>`;
  $("#qual").innerHTML="<tr><th>Measure</th><th>A</th><th>B</th></tr>"+[["Eye distance (px)","inter_ocular_px"],["Sharpness","sharpness"],["Brightness","brightness"],["Yaw (deg)","yaw"],["Pitch (deg)","pitch"]].map(([n,k])=>row(n,qa[k],qb[k])).join("")+row("Issues",esc([...qa.hard_issues,...qa.soft_issues].join("; ")||"none"),esc([...qb.hard_issues,...qb.soft_issues].join("; ")||"none"));
  $("#reg").innerHTML="<tr><th>Region</th><th>Points</th><th>Agreement</th><th></th></tr>"+g.regions.map(r=>`<tr><td>${r.name.replace(/_/g," ")}</td><td>${r.points}</td><td>${r.agreement}</td><td><div class="bar"><i style="width:${r.agreement}%"></i></div></td></tr>`).join("");
  $("#rat").innerHTML="<tr><th>Proportion</th><th>A</th><th>B</th><th>Difference</th></tr>"+g.ratios.map(r=>`<tr><td>${r.name}</td><td>${r.a}</td><td>${r.b}</td><td>${r.diff_pct} %</td></tr>`).join("");
  const ia=R.integrity.a,ib=R.integrity.b;
  $("#int").innerHTML="<tr><th>Indicator</th><th>A</th><th>B</th></tr>"+row("Result",ia.flag,ib.flag)+row("ELA mean / p99",ia.ela_mean+" / "+ia.ela_p99,ib.ela_mean+" / "+ib.ela_p99)+row("High-frequency ratio",ia.hf_ratio,ib.hf_ratio)+row("Detector probability",ia.model_probability??"not configured",ib.model_probability??"not configured")+row("Notes",esc(ia.notes.join("; ")||"none"),esc(ib.notes.join("; ")||"none"));
  $("#toggles").innerHTML=Object.entries(R.landmarks.regions).map(([k,v])=>`<label><input type="checkbox" data-r="${k}" checked> ${k.replace(/_/g," ")} (${v.length})</label>`).join("");
  document.querySelectorAll("[data-r]").forEach(cb=>cb.onchange=()=>{cb.checked?off.delete(cb.dataset.r):off.add(cb.dataset.r);draw()});
  $("#expiry").textContent="Case "+R.case_id+" is deleted automatically at "+R.expires_at+".";
  setMode("a");window.scrollTo({top:0})}

function setMode(m){mode=m;document.querySelectorAll(".tabs button").forEach(b=>b.setAttribute("aria-pressed",b.dataset.m===m));
  const i1=$("#img1"),i2=$("#img2");i1.src=R.images[m==="b"?"b":"a"];i2.src=R.images.b_aligned;
  i2.classList.toggle("hidden",m!=="o");$("#blendw").classList.toggle("hidden",m!=="o");i2.style.opacity=$("#blend").value/100;
  i1.onload=draw}
document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>setMode(b.dataset.m));
$("#blend").oninput=e=>$("#img2").style.opacity=e.target.value/100;

function draw(){const cv=$("#cv"),i=$("#img1");if(!i.naturalWidth)return;cv.width=i.naturalWidth;cv.height=i.naturalHeight;
  const x=cv.getContext("2d"),L=R.landmarks,keep=new Set();
  Object.entries(L.regions).forEach(([k,v])=>{if(!off.has(k))v.forEach(n=>keep.add(n))});
  const dots=(pts,col)=>{x.fillStyle=col;pts.forEach((p,n)=>{if(keep.has(n)){x.beginPath();x.arc(p[0],p[1],Math.max(1.6,cv.width/450),0,7);x.fill()}})};
  if(mode==="a")dots(L.a,"#0B7285");else if(mode==="b")dots(L.b,"#F5A01F");else{dots(L.a,"#0B7285");dots(L.b_aligned,"#F5A01F")}}

const dl=p=>{location.href=`/api/case/${R.case_id}/${p}`};
$("#pdf").onclick=()=>dl("report.pdf");$("#json").onclick=()=>dl("report.json");
$("#del").onclick=async()=>{await fetch("/api/case/"+R.case_id,{method:"DELETE"});reset()};
$("#again").onclick=reset;
function reset(){R=null;off.clear();delete files.a;delete files.b;document.querySelectorAll(".drop img").forEach(i=>i.remove());
  $("#gap").value="";$("#isgroup").checked=false;$("#fa").value="";$("#fb").value="";$("#consent").checked=false;ready();$("#results").classList.add("hidden");$("#intake").classList.remove("hidden")}




$("#loginform").onsubmit=async e=>{e.preventDefault();$("#lmsg").textContent="";
  const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username:$("#user").value,password:$("#pass").value})});
  const j=await r.json().catch(()=>({}));$("#pass").value="";r.ok?showApp(j):$("#lmsg").textContent=typeof j.detail==="string"?j.detail:"Sign-in failed."};
$("#logout").onclick=async()=>{await fetch("/api/logout",{method:"POST"});showLogin()};

let DESKTOP=false,CFG={},ME=null;
const hideAll=()=>["#login","#register","#intake","#scan","#results"].forEach(s=>$(s).classList.add("hidden"));
function needAuth(){R=null;DESKTOP?showRegister():showLogin()}
function showApp(u){hideAll();ME=u;$("#intake").classList.remove("hidden");
  $("#who").textContent=DESKTOP?u.name+", "+u.organisation:u.username+" ("+u.role+")";
  $("#logout").classList.toggle("hidden",DESKTOP);$("#edit").classList.toggle("hidden",!DESKTOP)}
function showLogin(){R=null;hideAll();$("#login").classList.remove("hidden");$("#logout").classList.add("hidden");$("#edit").classList.add("hidden");$("#who").textContent="Facial comparison with a forensic report"}
function showRegister(){hideAll();$("#register").classList.remove("hidden");const m=ME||{};
  for(const k of ["name","organisation","designation","email","phone","country"])$("#r_"+k).value=m[k]||"";if(m.purpose)$("#purpose").value=m.purpose;$("#r_terms").checked=false}
$("#regform").onsubmit=async e=>{e.preventDefault();$("#rmsg").textContent="";
  const body={accepted_terms:$("#r_terms").checked,share_consent:$("#r_share").checked,invite:$("#r_invite").value,purpose:$("#purpose").value};
  for(const k of ["name","organisation","designation","email","phone","country"])body[k]=$("#r_"+k).value;
  const r=await fetch("/api/register",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const d=await r.json().catch(()=>({}));
  if(!r.ok){$("#rmsg").textContent=typeof d.detail==="string"?d.detail:"Please check the details.";return}
  showApp(await (await fetch("/api/me")).json())};
$("#edit").onclick=showRegister;
async function init(){CFG=await (await fetch("/api/config")).json();DESKTOP=CFG.mode!=="server";$("#invitewrap").classList.toggle("hidden",!CFG.invite_required);$("#hostednote").classList.toggle("hidden",CFG.mode!=="hosted");
  $("#purpose").innerHTML=CFG.purposes.map(p=>`<option>${esc(p)}</option>`).join("");$("#sharewrap").classList.toggle("hidden",!CFG.share_enabled);
  const r=await fetch("/api/me");r.ok?showApp(await r.json()):needAuth()}
init();

if("serviceWorker" in navigator)navigator.serviceWorker.register("/sw.js").catch(()=>{});

let SCAN=null,SEL=-1;
function renderScan(){hideAll();$("#scan").classList.remove("hidden");SEL=-1;$("#gdo").disabled=true;$("#gmsg").textContent="";
  $("#scannotes").textContent=SCAN.faces.length+" faces found. Click a face in the photo, or choose from the ranked list. "+SCAN.notes.join(" ");
  const im=$("#gimg");im.onload=drawScan;im.src=SCAN.image;listScan()}
function listScan(){const f=SCAN.faces.map((x,i)=>({...x,i})).sort((a,b)=>a.rank-b.rank);
  $("#gtab").innerHTML="<tr><th>Rank</th><th>Face</th><th>Similarity</th><th>Size</th></tr>"+f.map(x=>`<tr data-i="${x.i}" style="cursor:pointer;${x.i===SEL?"background:#dfe9ed":""}"><td>${x.rank}</td><td>${x.i+1}</td><td>${x.cosine}</td><td>${x.size_px} px</td></tr>`).join("");
  document.querySelectorAll("#gtab tr[data-i]").forEach(t=>t.onclick=()=>pick(+t.dataset.i))}
function pick(i){SEL=i;$("#gdo").disabled=false;drawScan();listScan()}
function drawScan(){const cv=$("#gcv"),im=$("#gimg");if(!im.naturalWidth)return;cv.width=im.naturalWidth;cv.height=im.naturalHeight;
  const x=cv.getContext("2d"),lw=Math.max(2,cv.width/450);
  SCAN.faces.forEach((f,i)=>{const[a,b,c,d]=f.bbox,sel=i===SEL;x.lineWidth=sel?lw*2:lw;x.strokeStyle=sel?"#F5A01F":f.rank===1?"#0B7285":"#9aa7b0";x.strokeRect(a,b,c-a,d-b);
    x.font=`600 ${Math.max(14,cv.width/60)}px sans-serif`;x.fillStyle=x.strokeStyle;x.fillText(i+1,a,Math.max(16,b-4))})}
$("#gcv").onclick=e=>{const cv=$("#gcv"),r=cv.getBoundingClientRect(),px=(e.clientX-r.left)*cv.width/r.width,py=(e.clientY-r.top)*cv.height/r.height;
  let best=-1,area=1e18;SCAN.faces.forEach((f,i)=>{const[a,b,c,d]=f.bbox;if(px>=a&&px<=c&&py>=b&&py<=d&&(c-a)*(d-b)<area){area=(c-a)*(d-b);best=i}});if(best>=0)pick(best)};
$("#gback").onclick=()=>{hideAll();$("#intake").classList.remove("hidden")};
$("#gdo").onclick=async()=>{const fd=new FormData();fd.append("face",SEL);fd.append("case_ref",$("#ref").value);fd.append("examiner",$("#exa").value);fd.append("purpose",$("#pur").value);fd.append("age_gap",$("#gap").value);
  $("#gdo").disabled=true;$("#gmsg").textContent="Comparing the selected face...";
  try{const r=await fetch(`/api/scan/${SCAN.scan_id}/compare`,{method:"POST",body:fd});if(r.status===401){needAuth();return}const j=await r.json();
    if(!r.ok)throw new Error(typeof j.detail==="string"?j.detail:"The comparison failed.");R=j;$("#gmsg").textContent="";render()}catch(e){$("#gmsg").textContent=e.message}finally{$("#gdo").disabled=SEL<0}};

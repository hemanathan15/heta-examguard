const B=JSON.parse(document.getElementById('boot').textContent),csrf=document.querySelector('meta[name=csrf-token]').content;
const $=id=>document.getElementById(id);let cur=0,left=B.remaining,done=false;const ans={};B.questions.forEach(q=>{const s=B.saved[q.id];ans[q.id]=s?{sel:s.sel,marked:!!s.marked}:{sel:null,marked:false}});
async function api(path,body){const r=await fetch(`/api/session/${B.sid}/${path}`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body||{})});return r.json()}
function go(j){if(j&&j.redirect){done=true;if(document.fullscreenElement)document.exitFullscreen().catch(()=>{});location.href=j.redirect}}
function render(){const q=B.questions[cur],a=ans[q.id];$('qcount').textContent=`Question ${cur+1} of ${B.questions.length}`;$('qtext').textContent=q.text;
$('opts').innerHTML='';q.options.forEach((o,i)=>{const k='abcd'[i],b=document.createElement('button');b.className='choice'+(a.sel===k?' sel':'');b.textContent=`${k.toUpperCase()}. ${o}`;b.onclick=()=>{a.sel=a.sel===k?null:k;save(q.id);render()};$('opts').appendChild(b)});
$('mark').textContent=a.marked?'⚑ Unmark review':'⚑ Mark for review';$('prev').disabled=cur===0;$('next').disabled=cur===B.questions.length-1;
$('nav').innerHTML='';B.questions.forEach((x,i)=>{const b=document.createElement('button'),s=ans[x.id];b.textContent=i+1;b.className=(s.marked?'m ':s.sel?'a ':'')+(i===cur?'cur':'');b.onclick=()=>{cur=i;render()};$('nav').appendChild(b)})}
function save(id){return api('answer',{question_id:id,selected:ans[id].sel,marked:ans[id].marked}).then(go).catch(()=>{})}
$('prev').onclick=()=>{cur--;render()};$('next').onclick=()=>{cur++;render()};$('mark').onclick=()=>{const q=B.questions[cur];ans[q.id].marked=!ans[q.id].marked;save(q.id);render()};
$('submitBtn').onclick=()=>{const u=B.questions.filter(q=>!ans[q.id].sel).length,m=B.questions.filter(q=>ans[q.id].marked).length;$('modalMsg').textContent=`${u} unanswered, ${m} marked for review. You cannot change answers after submitting.`;$('modal').hidden=false};
$('cancel').onclick=()=>$('modal').hidden=true;
let submitting=false;async function submit(auto){if(submitting)return;submitting=true;$('confirm').disabled=true;go(await api('submit',{auto}))}
$('confirm').onclick=()=>submit(false);
function tick(){if(done)return;left--;const m=Math.max(left,0);$('timer').textContent=`${String(m/60|0).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`;$('timer').classList.toggle('low',left<=60);if(left<=0)submit(true)}
setInterval(tick,1000);tick();render();
window.EXAM={warn(msg){const w=$('warn');w.textContent='⚠️ '+msg;w.hidden=false;clearTimeout(w.t);w.t=setTimeout(()=>w.hidden=true,9000)},api,go,isDone:()=>done};

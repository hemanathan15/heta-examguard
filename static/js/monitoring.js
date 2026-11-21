(function(){const B=JSON.parse(document.getElementById('boot').textContent),E=window.EXAM;let last=0;
async function send(type,extra){if(E.isDone())return;try{const r=await E.api('event',Object.assign({type},extra||{}));if(r.message)E.warn(r.message);if(r.terminated||r.redirect)E.go(r)}catch(e){}}
// ---- navigation monitoring (limitations: cannot block OS/browser navigation, only detect it) ----
if(B.nav){const gate=document.getElementById('fsGate');
 const nav=(t,d)=>{const n=Date.now();if(n-last<2000)return;last=n;send(t,{detail:d})};
 if(document.documentElement.requestFullscreen){gate.hidden=false;document.getElementById('fsBtn').onclick=()=>{document.documentElement.requestFullscreen().catch(()=>{});gate.hidden=true}}
 document.addEventListener('visibilitychange',()=>{if(document.hidden)nav('tab_hidden','Tab hidden or window minimised')});
 document.addEventListener('fullscreenchange',()=>{if(!document.fullscreenElement&&!E.isDone()){nav('fullscreen_exit','Left fullscreen');gate.hidden=false}});
 window.addEventListener('blur',()=>setTimeout(()=>{if(!document.hidden&&!document.hasFocus())nav('window_blur','Window lost focus')},400));
 document.addEventListener('contextmenu',e=>e.preventDefault());}
// ---- camera monitoring (processed locally; no video is recorded or uploaded) ----
const st=document.getElementById('camStatus');if(!B.camera)return;
(async()=>{let stream;try{stream=await navigator.mediaDevices.getUserMedia({video:true});}catch(e){st.textContent='📷 blocked';send('camera_lost',{detail:'Camera permission denied'});return}
 const v=document.getElementById('cam');v.srcObject=stream;stream.getVideoTracks()[0].onended=()=>{st.textContent='📷 disconnected';send('camera_lost',{detail:'Camera track ended'})};
 st.textContent='📷 loading AI…';let model;try{model=await cocoSsd.load()}catch(e){st.textContent='📷 on (AI model unavailable)';return}
 let absentSince=null,absenceFlag=false,multi=0,phone=0,lastPhone=0,lastMulti=0,lastBeat=0,fails=0;
 setInterval(async()=>{if(E.isDone()||v.readyState<2)return;let p;try{p=await model.detect(v);fails=0}catch(e){if(++fails>5)st.textContent='📷 detector error';return}
  const persons=p.filter(x=>x.class==='person'&&x.score>.5).length,ph=p.filter(x=>x.class==='cell phone'&&x.score>=B.phoneConf);const n=Date.now();let face=persons===0?'absent':persons>1?'multiple':'present';
  st.textContent=face==='present'?'📷 face detected ✅':face==='absent'?'📷 no face ⚠️':'📷 multiple people ⚠️';
  if(persons===0){absentSince=absentSince||n;if(!absenceFlag&&n-absentSince>B.absence*1000){absenceFlag=true;send('face_absence',{detail:`Absent > ${B.absence}s`,face_status:face})}}else{absentSince=null;absenceFlag=false}
  multi=persons>1?multi+1:0;if(multi>=3&&n-lastMulti>30000){lastMulti=n;send('multiple_faces',{detail:`${persons} people`,face_status:face})}
  phone=ph.length?phone+1:0;if(phone>=2&&n-lastPhone>20000){lastPhone=n;send('phone',{detail:'Potential phone in view',confidence:ph[0].score,face_status:face})}
  if(n-lastBeat>10000){lastBeat=n;send('heartbeat',{face_status:face})}},1500);
})();})();

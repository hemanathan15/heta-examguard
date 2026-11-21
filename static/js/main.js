window.addEventListener('load',()=>setTimeout(()=>document.getElementById('loader')?.classList.add('hide'),350));
document.querySelectorAll('.count').forEach(el=>{const to=+el.dataset.to;let v=0;const t=setInterval(()=>{v+=Math.max(.5,to/50);if(v>=to){v=to;clearInterval(t)}el.textContent=Math.round(v)},25)});
setTimeout(()=>document.querySelectorAll('.flash').forEach(f=>f.remove()),6000);
(function(){const c=document.getElementById('brain');if(!c)return;const x=c.getContext('2d'),hero=c.dataset.mode==='hero';let W,H,N=[],P=[];
function build(){W=c.width=innerWidth;H=c.height=innerHeight;N=[];const n=hero?(W<700?60:110):40,cx=hero?W*.72:W/2,cy=H/2,rx=hero?Math.min(W*.22,230):Math.min(W*.4,520),ry=hero?Math.min(H*.3,200):H*.35;
for(let i=0;i<n;i++){const a=Math.random()*6.283,r=Math.sqrt(Math.random()),side=Math.random()<.5?-1:1;N.push({x:cx+side*rx*.5+Math.cos(a)*r*rx*.55+(Math.random()-.5)*20,y:cy+Math.sin(a)*r*ry,vx:(Math.random()-.5)*.15,vy:(Math.random()-.5)*.15,p:Math.random()*6})}}
function pulse(){const a=N[Math.random()*N.length|0],b=N.filter(o=>o!==a&&Math.hypot(o.x-a.x,o.y-a.y)<150);if(b.length)P.push({a,b:b[Math.random()*b.length|0],t:0})}
function frame(){x.clearRect(0,0,W,H);const al=hero?1:.45;N.forEach(n=>{n.x+=n.vx;n.y+=n.vy;n.p+=.03});
for(let i=0;i<N.length;i++)for(let j=i+1;j<N.length;j++){const d=Math.hypot(N[i].x-N[j].x,N[i].y-N[j].y);if(d<130){x.strokeStyle=`rgba(56,189,248,${(1-d/130)*.35*al})`;x.beginPath();x.moveTo(N[i].x,N[i].y);x.lineTo(N[j].x,N[j].y);x.stroke()}}
N.forEach(n=>{x.fillStyle=`rgba(34,211,238,${(.5+Math.sin(n.p)*.3)*al})`;x.beginPath();x.arc(n.x,n.y,2+Math.sin(n.p),0,6.283);x.fill()});
P=P.filter(p=>(p.t+=.03)<1);P.forEach(p=>{x.fillStyle=`rgba(167,139,250,${al})`;x.beginPath();x.arc(p.a.x+(p.b.x-p.a.x)*p.t,p.a.y+(p.b.y-p.a.y)*p.t,3,0,6.283);x.fill()});
if(Math.random()<(hero?.08:.03))pulse();requestAnimationFrame(frame)}
addEventListener('resize',build);build();frame()})();

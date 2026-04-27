import React, { useEffect, useRef, useState } from 'react';
import './ChatPage.css';
import { API_BASE, apiFetch } from '../../services/api.js';

function useRobot(canvasRef) {
  const apiRef = useRef({ setSpeaking: () => {}, setListening: () => {} });
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let speaking = false, listening = false, floatY = 0, floatDir = 1;
    let blinkT = 0, eyeClosed = false, glowT = 0, t = 0;
    let mouthOpenCurrent = 0, mouthOpenTarget = 0, mouthPhase = 0;
    let raf;
    const rr = (x,y,w,h,r) => { ctx.beginPath(); ctx.roundRect(x,y,w,h,r); ctx.fill(); };
    function drawBody(cx,cy){ctx.save();ctx.shadowColor='rgba(0,0,0,0.3)';ctx.shadowBlur=24;ctx.shadowOffsetY=6;const g=ctx.createRadialGradient(cx-30,cy-28,0,cx,cy,95);g.addColorStop(0,'#FAFBFF');g.addColorStop(.35,'#F0F2FA');g.addColorStop(.7,'#DCDEE8');g.addColorStop(1,'#B8BAC8');ctx.fillStyle=g;ctx.beginPath();ctx.ellipse(cx,cy,86,96,0,0,Math.PI*2);ctx.fill();ctx.shadowColor='transparent';const gh=ctx.createRadialGradient(cx-22,cy-38,0,cx-22,cy-38,38);gh.addColorStop(0,'rgba(255,255,255,0.55)');gh.addColorStop(1,'rgba(255,255,255,0)');ctx.fillStyle=gh;ctx.beginPath();ctx.ellipse(cx-25,cy-35,28,20,-.3,0,Math.PI*2);ctx.fill();ctx.restore();}
    function drawArm(ax,ay,side){ctx.save();ctx.shadowColor='rgba(0,0,0,0.25)';ctx.shadowBlur=16;ctx.shadowOffsetX=side*5;ctx.shadowOffsetY=5;const g=ctx.createRadialGradient(ax-side*10,ay-16,0,ax,ay,40);g.addColorStop(0,'#FAFBFF');g.addColorStop(.4,'#ECEEF8');g.addColorStop(1,'#B8BAC8');ctx.fillStyle=g;ctx.beginPath();ctx.ellipse(ax,ay,24,48,side*.15,0,Math.PI*2);ctx.fill();ctx.restore();}
    function drawNeck(cx,cy){ctx.save();const g=ctx.createLinearGradient(cx-12,cy,cx+12,cy);g.addColorStop(0,'#C8CAD8');g.addColorStop(.5,'#E8EAF2');g.addColorStop(1,'#C0C2D0');ctx.fillStyle=g;rr(cx-12,cy,24,20,4);ctx.restore();}
    function drawHead(cx,cy){ctx.save();ctx.shadowColor='rgba(0,0,0,0.35)';ctx.shadowBlur=28;ctx.shadowOffsetY=8;const g=ctx.createRadialGradient(cx-25,cy-42,0,cx,cy-28,86);g.addColorStop(0,'#FFFFFF');g.addColorStop(.35,'#F2F4FA');g.addColorStop(.7,'#DDDFE8');g.addColorStop(1,'#C0C2D0');ctx.fillStyle=g;rr(cx-74,cy-74,148,96,30);ctx.shadowColor='transparent';for(const s of[-1,1]){const ex=cx+s*68,ey=cy-36;const eg=ctx.createRadialGradient(ex-s*7,ey-5,0,ex,ey,16);eg.addColorStop(0,'#F0F2FA');eg.addColorStop(1,'#C0C2D0');ctx.fillStyle=eg;rr(ex-11,ey-18,22,34,7)}const gh=ctx.createRadialGradient(cx-22,cy-58,0,cx-22,cy-58,32);gh.addColorStop(0,'rgba(255,255,255,0.65)');gh.addColorStop(1,'rgba(255,255,255,0)');ctx.fillStyle=gh;ctx.beginPath();ctx.ellipse(cx-22,cy-58,26,16,-.2,0,Math.PI*2);ctx.fill();ctx.restore();}
    function drawScreen(cx,cy){ctx.save();const sg=ctx.createRadialGradient(cx,cy-30,0,cx,cy-30,60);sg.addColorStop(0,'#0A1628');sg.addColorStop(.6,'#060E1C');sg.addColorStop(1,'#030810');ctx.fillStyle=sg;rr(cx-58,cy-64,116,66,16);const gl=ctx.createLinearGradient(cx-56,cy-62,cx-56,cy-42);gl.addColorStop(0,'rgba(0,201,228,0.07)');gl.addColorStop(1,'rgba(0,201,228,0)');ctx.fillStyle=gl;rr(cx-56,cy-62,112,28,14);ctx.restore();}
    function drawEyes(cx,cy){for(const ex of[cx-20,cx+20]){const ey=cy-40,ew=16,eh=eyeClosed?3:14;if(!eyeClosed){const gs=.35+glowT*.25;const eg=ctx.createRadialGradient(ex,ey,0,ex,ey,20);eg.addColorStop(0,`rgba(0,180,210,${gs*.35})`);eg.addColorStop(1,'rgba(0,180,210,0)');ctx.fillStyle=eg;ctx.beginPath();ctx.ellipse(ex,ey,20,18,0,0,Math.PI*2);ctx.fill();const ec=ctx.createRadialGradient(ex-3,ey-3,0,ex,ey,10);ec.addColorStop(0,'#00C9E4');ec.addColorStop(.5,'#0099B4');ec.addColorStop(1,'#006070');ctx.fillStyle=ec;ctx.beginPath();ctx.ellipse(ex,ey-1,ew/2,eh/2+1,0,Math.PI,0);ctx.ellipse(ex,ey-1,ew/2,eh/2-2,0,0,Math.PI);ctx.closePath();ctx.fill();const er=ctx.createRadialGradient(ex+3,ey-5,0,ex+3,ey-5,4);er.addColorStop(0,'rgba(255,255,255,0.7)');er.addColorStop(1,'rgba(255,255,255,0)');ctx.fillStyle=er;ctx.beginPath();ctx.ellipse(ex+3,ey-5,4,2.5,0,0,Math.PI*2);ctx.fill()}else{ctx.strokeStyle='#0099B4';ctx.lineWidth=2;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(ex-ew/2+2,ey);ctx.lineTo(ex+ew/2-2,ey);ctx.stroke()}}}
    function drawMouth(cx,cy){const m=mouthOpenCurrent,mx=cx,my=cy-12,w=18+m*7,hB=m*10,hT=m*2.5;ctx.save();if(m>.04){ctx.beginPath();ctx.moveTo(mx-w,my);ctx.bezierCurveTo(mx-w*.5,my+hB*1.2,mx+w*.5,my+hB*1.2,mx+w,my);ctx.bezierCurveTo(mx+w*.5,my-hT,mx-w*.5,my-hT,mx-w,my);ctx.closePath();const bg=ctx.createRadialGradient(mx,my+hB*.3,0,mx,my+hB*.5,w);bg.addColorStop(0,'#001520');bg.addColorStop(1,'#000810');ctx.fillStyle=bg;ctx.fill()}const lb=ctx.createLinearGradient(mx-w,my,mx+w,my);lb.addColorStop(0,'#006070');lb.addColorStop(.5,'#00C9E4');lb.addColorStop(1,'#006070');ctx.strokeStyle=lb;ctx.lineWidth=2;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(mx-w,my);ctx.bezierCurveTo(mx-w*.5,my+hB*1.1,mx+w*.5,my+hB*1.1,mx+w,my);ctx.stroke();const lt=ctx.createLinearGradient(mx-w,my,mx+w,my);lt.addColorStop(0,'#004A5A');lt.addColorStop(.5,'#009AB0');lt.addColorStop(1,'#004A5A');ctx.strokeStyle=lt;ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(mx-w,my);ctx.bezierCurveTo(mx-w*.5,my-4+m*2.5,mx+w*.5,my-4+m*2.5,mx+w,my);ctx.stroke();ctx.restore();}
    function drawAntenna(cx,cy){const ax=cx,ay=cy-74;ctx.save();const tg=ctx.createLinearGradient(ax-4,ay,ax+4,ay);tg.addColorStop(0,'#C0C2D0');tg.addColorStop(.5,'#E8EAF2');tg.addColorStop(1,'#C0C2D0');ctx.fillStyle=tg;rr(ax-4,ay-18,8,20,3);const bg=ctx.createRadialGradient(ax-2,ay-20,0,ax,ay-16,10);bg.addColorStop(0,'#E8EAF2');bg.addColorStop(1,'#B0B2C0');ctx.fillStyle=bg;rr(ax-7,ay-24,14,9,3);ctx.restore();}
    function drawRobot(){ctx.clearRect(0,0,canvas.width,canvas.height);const cx=180,cy=200+floatY;const s0=ctx.createRadialGradient(cx,390,0,cx,390,90);s0.addColorStop(0,`rgba(0,0,0,${0.15-Math.abs(floatY)*.007})`);s0.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=s0;ctx.beginPath();ctx.ellipse(cx,390,90,12,0,0,Math.PI*2);ctx.fill();drawArm(cx-88,cy+28,-1);drawArm(cx+88,cy+28,1);drawBody(cx,cy+55);drawNeck(cx,cy+8);drawHead(cx,cy);drawScreen(cx,cy);drawEyes(cx,cy);drawMouth(cx,cy);drawAntenna(cx,cy)}
    function animate(){raf=requestAnimationFrame(animate);t+=.02;floatY+=.22*floatDir;if(Math.abs(floatY)>8)floatDir*=-1;glowT=(Math.sin(t*2)+1)/2;blinkT++;if(blinkT===160)eyeClosed=true;if(blinkT===167){eyeClosed=false;blinkT=0}if(speaking){mouthPhase+=.18;mouthOpenTarget=.35+Math.sin(mouthPhase*1.7)*.28+Math.sin(mouthPhase*3.1)*.12+Math.sin(mouthPhase*.8)*.10;mouthOpenTarget=Math.max(.05,Math.min(1,mouthOpenTarget))}else{mouthOpenTarget=0;mouthPhase=0}const spd=mouthOpenTarget>mouthOpenCurrent?.18:.10;mouthOpenCurrent+=(mouthOpenTarget-mouthOpenCurrent)*spd;drawRobot()}
    apiRef.current = { setSpeaking: v => { speaking = v; listening = false; }, setListening: v => { listening = v; speaking = false; } };
    animate();
    return () => cancelAnimationFrame(raf);
  }, [canvasRef]);
  return apiRef;
}

export default function ChatPage() {
  const canvasRef = useRef(null);
  const robot = useRobot(canvasRef);
  const [loading, setLoading] = useState(true);
  const [loadPct, setLoadPct] = useState(0);
  const [loadText, setLoadText] = useState('INITIALISATION');
  const [chatHidden, setChatHidden] = useState(false);
  const [status, setStatus] = useState('Chargement...');
  const [dot, setDot] = useState('');
  const [lang, setLang] = useState('fr');
  const [historyLen, setHistoryLen] = useState(0);
  const [messages, setMessages] = useState([{ role: 'izzy', text: "Bonjour ! Je suis Izzy 👋\nComment puis-je vous aider aujourd'hui ?" }]);
  const [vocalInput, setVocalInput] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [speaking, setSpeakingState] = useState(false);
  const [listening, setListening] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const sessionRef = useRef(localStorage.getItem('izzy_session') || crypto.randomUUID());
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const bottomRef = useRef(null);

  useEffect(() => { localStorage.setItem('izzy_session', sessionRef.current); setLoadPct(100); setLoadText('PRÊTE'); const t=setTimeout(()=>{setLoading(false); setDot('ready'); setStatus('Prête');}, 700); return()=>clearTimeout(t); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  function setRobotSpeaking(v) { robot.current.setSpeaking(v); setSpeakingState(v); setDot(v ? 'talking' : 'ready'); setStatus(v ? 'Izzy parle...' : 'Prête'); }
  function setListUI(v) { robot.current.setListening(v); setListening(v); setDot(v ? 'listen' : 'ready'); }
  function setDetUI(v) { setDetecting(v); setDot(v ? 'listen' : 'ready'); }
  function addMsg(text, role) { setMessages(prev => [...prev, { text, role }]); }
  function syncLip(audio, meta = []) { let i=0; const tick=()=>{ if(!audio.paused && i<meta.length){ const ct=audio.currentTime,w=meta[i]; robot.current.setSpeaking(ct>=w.start&&ct<=w.end); if(ct>w.end)i++; } if(!audio.ended) requestAnimationFrame(tick);}; tick(); }

  async function askIzzy(q) {
    if (busy || !q.trim()) return;
    setBusy(true); addMsg(q, 'user'); setDot('talking'); setStatus('Réflexion...');
    try {
      const d = await apiFetch('/ask', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({question:q, session_id: sessionRef.current}) });
      addMsg(d.answer, 'izzy'); setLang(d.lang || 'fr'); setHistoryLen(d.history_len || 0);
      if (d.audio_url) {
        setRobotSpeaking(true);
        const aud = new Audio(`${API_BASE}${d.audio_url}`);
        aud.onended = () => { robot.current.setSpeaking(false); setRobotSpeaking(false); setBusy(false); };
        aud.onerror = () => { robot.current.setSpeaking(false); setRobotSpeaking(false); setBusy(false); };
        aud.play().then(()=>syncLip(aud, d.metadata || [])).catch(()=>{ robot.current.setSpeaking(false); setRobotSpeaking(false); setBusy(false); });
      } else { setRobotSpeaking(false); setBusy(false); }
    } catch (e) { robot.current.setSpeaking(false); setRobotSpeaking(false); setBusy(false); addMsg('❌ Erreur : ' + e.message, 'izzy'); }
  }

  async function resetConversation() { await apiFetch('/reset', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({session_id:sessionRef.current})}); setHistoryLen(0); setMessages([{role:'izzy', text:'Conversation réinitialisée 👋'}]); }
  function newChat() { sessionRef.current = crypto.randomUUID(); localStorage.setItem('izzy_session', sessionRef.current); setMessages([{role:'izzy', text:'Nouveau chat démarré 👋\nComment puis-je vous aider ?'}]); setHistoryLen(0); setVocalInput(''); setChatInput(''); setLang('fr'); setBusy(false); setRobotSpeaking(false); }
  function sendVocal(){ const q=vocalInput.trim(); if(!q)return; setVocalInput(''); askIzzy(q); }
  function sendChat(){ const q=chatInput.trim(); if(!q)return; setChatInput(''); askIzzy(q); }

  async function toggleMic(){
    if(busy)return; if(!navigator.mediaDevices){alert('Utilisez Chrome pour le mode vocal.');return;}
    if(listening){ if(recorderRef.current && recorderRef.current.state !== 'inactive') recorderRef.current.stop(); return; }
    try { streamRef.current = await navigator.mediaDevices.getUserMedia({audio:true}); } catch(e){ alert('Accès micro refusé.'); return; }
    const mediaRecorder = new MediaRecorder(streamRef.current); recorderRef.current = mediaRecorder; chunksRef.current=[]; setListUI(true); setStatus('Parlez... (recliquer pour arrêter)');
    mediaRecorder.ondataavailable = e => { if(e.data.size>0) chunksRef.current.push(e.data); };
    mediaRecorder.onstop = async () => { streamRef.current?.getTracks().forEach(t=>t.stop()); setListUI(false); setDetUI(true); setStatus('Whisper analyse...'); const blob=new Blob(chunksRef.current,{type:'audio/webm'}); const fd=new FormData(); fd.append('audio',blob,'audio.webm'); try{ const d = await apiFetch('/transcribe',{method:'POST',body:fd}); setDetUI(false); if(!d.text?.trim()){setStatus('Pas compris'); setTimeout(()=>setStatus('Prête'),2500); return;} setVocalInput(d.text); setStatus('Prête'); askIzzy(d.text);}catch(e){setDetUI(false); setStatus('Erreur transcription'); setTimeout(()=>setStatus('Prête'),2500);} };
    mediaRecorder.start();
  }

  return <>
  <div className="chat-page">
    <div id="loading" className={loading ? '' : 'out'}><div className="ld-logo">IZ<span>Z</span>Y</div><div className="ld-track"><div className="ld-bar" style={{width:`${loadPct}%`}} /></div><div className="ld-hint">{loadText}</div></div>
    <div className="corner tl"></div><div className="corner bl"></div><div className="corner tr"></div>
    <div id="app" className={chatHidden ? 'chat-hidden' : ''}>
      <header id="header"><div className="h-brand"><div className="h-diamond"></div><div><div className="h-name">IZZY</div><div className="h-sub">DJEZZY AI ASSISTANT</div></div></div><div className="h-center">{['fr','ar','en'].map(l=><span key={l} className={'lang-tag '+(lang===l?'active':'')} id={`lang-${l}`}>{l.toUpperCase()}</span>)}</div><div className="h-right"><span className="h-badge">{historyLen} échange(s)</span><div id="status-wrap"><div id="status-dot" className={dot}></div><span id="status-txt">{status}</span></div><button className="h-btn" onClick={()=>setChatHidden(!chatHidden)}>{chatHidden?'Afficher chat':'Masquer chat'}</button></div></header>
      <main id="avatar-zone"><canvas ref={canvasRef} id="robot-canvas" width="360" height="400"></canvas><div id="bars" className={speaking?'on':''}>{Array.from({length:11}).map((_,i)=><div key={i} className={'b '+(speaking?'on':'')}></div>)}</div><div id="av-name"><h2>IZZY</h2><p>ASSISTANTE IA · DJEZZY</p></div><div id="bottom-input"><div className="input-shell"><input value={vocalInput} onChange={e=>setVocalInput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')sendVocal()}} type="text" placeholder="Posez votre question à Izzy..." autoComplete="off"/><button className={'icon-btn mic-btn '+(listening?'listening ':'')+(detecting?'detecting':'')} onClick={toggleMic}>🎙</button><button className="icon-btn send-btn" onClick={sendVocal}>➤</button></div></div></main>
      <aside id="chat-zone"><div id="chat-head"><span className="ch-title"><span>●</span> CONVERSATION</span><div className="ch-actions"><button className="sm-btn new" onClick={newChat}>＋ NOUVEAU</button><button className="sm-btn" onClick={resetConversation}>↺ RESET</button></div></div><div id="messages">{messages.map((m,i)=><div key={i} className={'msg '+m.role}>{m.text.split('\n').map((line,j)=><React.Fragment key={j}>{line}{j<m.text.split('\n').length-1 && <br/>}</React.Fragment>)}</div>)}<div ref={bottomRef}/></div><div id="chat-input-wrap"><div className="chat-shell"><input value={chatInput} onChange={e=>setChatInput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')sendChat()}} type="text" placeholder="Votre message..." autoComplete="off"/><button className={'icon-btn mic-btn '+(listening?'listening ':'')+(detecting?'detecting':'')} onClick={toggleMic}>🎙</button><button className="icon-btn send-btn" onClick={sendChat}>➤</button></div></div></aside>
    </div>
  </div>
  </>;
}

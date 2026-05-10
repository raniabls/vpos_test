import React, { useEffect, useRef, useState } from 'react';
import './App.css';
import { API_BASE, apiFetch } from './api.js';
import RobotCanvas from './RobotCanvas.jsx';

export default function App() {
  const robot = useRef({
    setSpeaking: () => {},
    setListening: () => {},
  });

  const sessionRef = useRef(localStorage.getItem('izzy_session') || crypto.randomUUID());
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const bottomRef = useRef(null);

  const [loading, setLoading] = useState(true);
  const [loadPct, setLoadPct] = useState(0);
  const [loadText, setLoadText] = useState('INITIALISATION');

  const [chatHidden, setChatHidden] = useState(false);
  const [status, setStatus] = useState('Chargement...');
  const [dot, setDot] = useState('');
  const [lang, setLang] = useState('fr');
  const [historyLen, setHistoryLen] = useState(0);

  const [messages, setMessages] = useState([
    {
      role: 'izzy',
      text: "Bonjour ! Je suis Izzy 👋\nComment puis-je vous aider aujourd'hui ?",
    },
  ]);

  const [vocalInput, setVocalInput] = useState('');
  const [chatInput, setChatInput] = useState('');

  const [busy, setBusy] = useState(false);
  const [speaking, setSpeakingState] = useState(false);
  const [listening, setListening] = useState(false);
  const [detecting, setDetecting] = useState(false);

  useEffect(() => {
    localStorage.setItem('izzy_session', sessionRef.current);

    setLoadPct(100);
    setLoadText('PRÊTE');

    const t = setTimeout(() => {
      setLoading(false);
      setDot('ready');
      setStatus('Prête');
    }, 700);

    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  function setRobotSpeaking(v) {
    robot.current.setSpeaking(v);
    setSpeakingState(v);
    setDot(v ? 'talking' : 'ready');
    setStatus(v ? 'Izzy parle...' : 'Prête');
  }

  function setListUI(v) {
    robot.current.setListening(v);
    setListening(v);
    setDot(v ? 'listen' : 'ready');
  }

  function setDetUI(v) {
    setDetecting(v);
    setDot(v ? 'listen' : 'ready');
  }

  function addMsg(text, role) {
    setMessages(prev => [...prev, { text, role }]);
  }

  function syncLip(audio, meta = []) {
    let i = 0;

    const tick = () => {
      if (!audio.paused && i < meta.length) {
        const ct = audio.currentTime;
        const w = meta[i];

        robot.current.setSpeaking(ct >= w.start && ct <= w.end);

        if (ct > w.end) i++;
      }

      if (!audio.ended) requestAnimationFrame(tick);
    };

    tick();
  }

  async function askIzzy(q) {
    if (busy || !q.trim()) return;

    setBusy(true);
    addMsg(q, 'user');
    setDot('talking');
    setStatus('Réflexion...');

    try {
      const d = await apiFetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: q,
          session_id: sessionRef.current,
        }),
      });

      addMsg(d.answer, 'izzy');
      setLang(d.lang || 'fr');
      setHistoryLen(d.history_len || 0);

      if (d.audio_url) {
        setRobotSpeaking(true);

        const aud = new Audio(`${API_BASE}${d.audio_url}`);

        aud.onended = () => {
          robot.current.setSpeaking(false);
          setRobotSpeaking(false);
          setBusy(false);
        };

        aud.onerror = () => {
          robot.current.setSpeaking(false);
          setRobotSpeaking(false);
          setBusy(false);
        };

        aud
          .play()
          .then(() => syncLip(aud, d.metadata || []))
          .catch(() => {
            robot.current.setSpeaking(false);
            setRobotSpeaking(false);
            setBusy(false);
          });
      } else {
        setRobotSpeaking(false);
        setBusy(false);
      }
    } catch (e) {
      robot.current.setSpeaking(false);
      setRobotSpeaking(false);
      setBusy(false);
      addMsg('❌ Erreur : ' + e.message, 'izzy');
    }
  }

  async function resetConversation() {
    await apiFetch('/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionRef.current,
      }),
    });

    setHistoryLen(0);
    setMessages([{ role: 'izzy', text: 'Conversation réinitialisée 👋' }]);
  }

  function newChat() {
    sessionRef.current = crypto.randomUUID();
    localStorage.setItem('izzy_session', sessionRef.current);

    setMessages([
      {
        role: 'izzy',
        text: 'Nouveau chat démarré 👋\nComment puis-je vous aider ?',
      },
    ]);

    setHistoryLen(0);
    setVocalInput('');
    setChatInput('');
    setLang('fr');
    setBusy(false);
    setRobotSpeaking(false);
  }

  function sendVocal() {
    const q = vocalInput.trim();
    if (!q) return;

    setVocalInput('');
    askIzzy(q);
  }

  function sendChat() {
    const q = chatInput.trim();
    if (!q) return;

    setChatInput('');
    askIzzy(q);
  }

async function toggleMic() {
    if (busy) return;

    if (!navigator.mediaDevices) {
      alert('Utilisez Chrome pour le mode vocal.');
      return;
    }

    if (listening) {
      if (recorderRef.current && recorderRef.current.state !== 'inactive') {
        recorderRef.current.stop();
      }
      return;
    }

    try {
      streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      alert('Accès micro refusé.');
      return;
    }
    

    const mediaRecorder = new MediaRecorder(streamRef.current);
    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(streamRef.current);

    const analyser = audioContext.createAnalyser();
    source.connect(analyser);

    analyser.fftSize = 2048;

    const dataArray = new Uint8Array(analyser.fftSize);

    let silenceStart = null;
    const silenceDelay = 5000; // 5 SEC
    const silenceThreshold = 8;

    function detectSilence() {
     if (mediaRecorder.state === 'inactive') return;

      analyser.getByteTimeDomainData(dataArray);

     let max = 0;

     for (let i = 0; i < dataArray.length; i++) {
      const v = Math.abs(dataArray[i] - 128);

      if (v > max) max = v;
     }
  
     if (max < silenceThreshold) {
      if (!silenceStart) {
      silenceStart = Date.now();
      }

      const silenceTime = Date.now() - silenceStart;

       if (silenceTime > silenceDelay) {
        mediaRecorder.stop();
        return;
      }
     } else {
       silenceStart = null;
     } 

     requestAnimationFrame(detectSilence);
    }   
    recorderRef.current = mediaRecorder;
    chunksRef.current = [];

    setListUI(true);
    setStatus('Parlez... (recliquer pour arrêter)');

    mediaRecorder.ondataavailable = e => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      streamRef.current?.getTracks().forEach(t => t.stop());

      setListUI(false);
      setDetUI(true);
      setStatus('Whisper analyse...');

      const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
      const fd = new FormData();
      fd.append('audio', blob, 'audio.webm');

      try {
        const d = await apiFetch('/transcribe', {
          method: 'POST',
          body: fd,
        });

        setDetUI(false);

        if (!d.text?.trim()) {
          setStatus('Pas compris');
          setTimeout(() => setStatus('Prête'), 2500);
          return;
        }

        setVocalInput(d.text);
        setStatus('Prête');
        askIzzy(d.text);
      } catch (e) {
        setDetUI(false);
        setStatus('Erreur transcription');
        setTimeout(() => setStatus('Prête'), 2500);
      }
    };

    mediaRecorder.start();
    detectSilence();
  }

  return (
    <>
      <div className="chat-page">
        <div id="loading" className={loading ? '' : 'out'}>
          <div className="ld-logo">
            IZ<span>Z</span>Y
          </div>

          <div className="ld-track">
            <div
              className="ld-bar"
              style={{ width: `${loadPct}%` }}
            />
          </div>

          <div className="ld-hint">{loadText}</div>
        </div>

        <div className="corner tl"></div>
        <div className="corner bl"></div>
        <div className="corner tr"></div>

        <div id="app" className={chatHidden ? 'chat-hidden' : ''}>
          <header id="header">
            <div className="h-brand">
              <div className="h-diamond"></div>

              <div>
                <div className="h-name">IZZY</div>
                <div className="h-sub">DJEZZY AI ASSISTANT</div>
              </div>
            </div>

            <div className="h-center">
              {['fr', 'ar', 'en'].map(l => (
                <span
                  key={l}
                  className={'lang-tag ' + (lang === l ? 'active' : '')}
                  id={`lang-${l}`}
                >
                  {l.toUpperCase()}
                </span>
              ))}
            </div>

            <div className="h-right">
              <span className="h-badge">
                {historyLen} échange(s)
              </span>

              <div id="status-wrap">
                <div id="status-dot" className={dot}></div>
                <span id="status-txt">{status}</span>
              </div>

              <button
                className="h-btn"
                onClick={() => setChatHidden(!chatHidden)}
              >
                {chatHidden ? 'Afficher chat' : 'Masquer chat'}
              </button>
            </div>
          </header>

          <main id="avatar-zone">
            <RobotCanvas
              speaking={speaking}
              robotRef={robot}
            />

          </main>            <button
    className={
      'avatar-talk-btn ' +
      (listening ? 'listening ' : '') +
      (detecting ? 'detecting' : '')
    }
    onClick={toggleMic}
    disabled={busy}
  >
    <span className="talk-icon">🎙</span>
  </button>

          <aside id="chat-zone">
            <div id="chat-head">
              <span className="ch-title">
                <span>●</span> CONVERSATION
              </span>

              <div className="ch-actions">
                <button
                  className="sm-btn new"
                  onClick={newChat}
                >
                  ＋ NOUVEAU
                </button>

                <button
                  className="sm-btn"
                  onClick={resetConversation}
                >
                  ↺ RESET
                </button>
              </div>
            </div>

            <div id="messages">
              {messages.map((m, i) => (
                <div key={i} className={'msg ' + m.role}>
                  {m.text.split('\n').map((line, j) => (
                    <React.Fragment key={j}>
                      {line}
                      {j < m.text.split('\n').length - 1 && <br />}
                    </React.Fragment>
                  ))}
                </div>
              ))}

              <div ref={bottomRef} />
            </div>

            <div id="chat-input-wrap">
              <div className="chat-shell">
                <input
                  value={chatInput}
                  onChange={e => setChatInput(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') sendChat();
                  }}
                  type="text"
                  placeholder="Votre message..."
                  autoComplete="off"
                />

                <button
                  className={
                    'icon-btn mic-btn ' +
                    (listening ? 'listening ' : '') +
                    (detecting ? 'detecting' : '')
                  }
                  onClick={toggleMic}
                >
                  🎙
                </button>

                <button
                  className="icon-btn send-btn"
                  onClick={sendChat}
                >
                  ➤
                </button>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </>
  );
}
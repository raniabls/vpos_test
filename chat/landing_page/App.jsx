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
  const currentAudioRef = useRef(null);
  const requestAbortRef = useRef(null);
  const askRunRef = useRef(0);

  const [isMuted, setIsMuted] = useState(() => {
    return localStorage.getItem('izzy_muted') === 'true';
  });

  const toggleMute = () => {
    const newMuted = !isMuted;
    setIsMuted(newMuted);
    localStorage.setItem('izzy_muted', String(newMuted));
    if (currentAudioRef.current) {
      currentAudioRef.current.muted = newMuted;
    }
  };

  const stopCurrentAudio = () => {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current.currentTime = 0;
      currentAudioRef.current.src = '';
      currentAudioRef.current = null;
    }

    robot.current.setSpeaking(false);
    setSpeakingState(false);
    setDot('ready');
    setStatus('Prête');
  };

  const [loading, setLoading] = useState(true);
  const [loadPct, setLoadPct] = useState(0);
  const [loadText, setLoadText] = useState('INITIALISATION');

  const [chatHidden, setChatHidden] = useState(true);
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
  const recommendations = [
    { label: '❓ FAQ', question: 'Quelles sont les questions fréquentes sur Djezzy ?' },
    { label: '📦 Offres 1000 DA', question: 'Quelles offres sont disponibles autour de 1000 DA ?' },
    { label: '🌐 Internet', question: 'Je veux une offre internet, que me proposes-tu ?' },
    { label: '🛠️ Services', question: 'Quels services Djezzy peux-tu expliquer ?' },
  ];


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
    const question = q.trim();
    if (!question) return;

    // Interrompre immédiatement l'audio en cours.
    stopCurrentAudio();

    // Annuler l'ancien fetch si une ancienne requête est encore en cours.
    if (requestAbortRef.current) {
      requestAbortRef.current.abort();
    }

    const controller = new AbortController();
    requestAbortRef.current = controller;

    // ID de requête : permet d'ignorer toute ancienne réponse arrivée en retard.
    const runId = askRunRef.current + 1;
    askRunRef.current = runId;

    setBusy(true);
    addMsg(question, 'user');
    setDot('talking');
    setStatus('Réflexion...');

    try {
      const d = await apiFetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          question,
          session_id: sessionRef.current,
        }),
      });

      // Si une nouvelle question a été envoyée entre temps, on ignore cette ancienne réponse.
      if (runId !== askRunRef.current) return;

      addMsg(d.answer, 'izzy');
      setLang(d.lang || 'fr');
      setHistoryLen(d.history_len || 0);

      if (d.audio_url) {
        setRobotSpeaking(true);

        const aud = new Audio(`${API_BASE}${d.audio_url}`);
        aud.muted = isMuted;
        currentAudioRef.current = aud;

        aud.onended = () => {
          if (runId !== askRunRef.current) return;

          if (currentAudioRef.current === aud) {
            currentAudioRef.current = null;
          }

          robot.current.setSpeaking(false);
          setRobotSpeaking(false);
          setBusy(false);
        };

        aud.onerror = () => {
          if (runId !== askRunRef.current) return;

          if (currentAudioRef.current === aud) {
            currentAudioRef.current = null;
          }

          robot.current.setSpeaking(false);
          setRobotSpeaking(false);
          setBusy(false);
        };

        aud
          .play()
          .then(() => {
            if (runId === askRunRef.current) {
              syncLip(aud, d.metadata || []);
            }
          })
          .catch(() => {
            if (runId !== askRunRef.current) return;

            if (currentAudioRef.current === aud) {
              currentAudioRef.current = null;
            }

            robot.current.setSpeaking(false);
            setRobotSpeaking(false);
            setBusy(false);
          });
      } else {
        setRobotSpeaking(false);
        setBusy(false);
      }
    } catch (e) {
      if (e.name === 'AbortError') return;
      if (runId !== askRunRef.current) return;

      robot.current.setSpeaking(false);
      setRobotSpeaking(false);
      setBusy(false);
      addMsg('❌ Erreur : ' + e.message, 'izzy');
    } finally {
      if (requestAbortRef.current === controller) {
        requestAbortRef.current = null;
      }
    }
  }

  async function resetConversation() {
    stopCurrentAudio();
    // await apiFetch('/reset', {
    //   method: 'POST',
    //   headers: { 'Content-Type': 'application/json' },
    //   body: JSON.stringify({
    //     session_id: sessionRef.current,
    //   }),
    // });

    setHistoryLen(0);
    setMessages([{ role: 'izzy', text: 'Conversation réinitialisée 👋' }]);
  }

  function newChat() {
    stopCurrentAudio();

    if (requestAbortRef.current) {
      requestAbortRef.current.abort();
      requestAbortRef.current = null;
    }

    askRunRef.current += 1;

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

  function openChat() {
    setChatHidden(false);
  }

  function sendRecommendation(question) {
    if (!question?.trim()) return;

    setChatHidden(false);
    setChatInput('');
    askIzzy(question);
  }

  async function toggleMic() {
    if (busy && currentAudioRef.current) {
      stopCurrentAudio();
      setBusy(false);
    } else if (busy) {
      return;
    }

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
                className={`h-btn sound-btn ${isMuted ? 'muted' : 'active'}`}
                onClick={toggleMute}
                title={isMuted ? "Activer le son" : "Désactiver le son"}
              >
                {isMuted ? (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                    <line x1="23" y1="9" x2="17" y2="15"></line>
                    <line x1="17" y1="9" x2="23" y2="15"></line>
                  </svg>
                ) : (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                    <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
                  </svg>
                )}
              </button>

              <button
                className="h-btn"
                onClick={() => setChatHidden(!chatHidden)}
              >
                {chatHidden ? 'Afficher chat' : 'Masquer chat'}
              </button>
            </div>
          </header>

<main id="avatar-zone">
  <div className="robot-wrapper">
    <RobotCanvas
      speaking={speaking}
      robotRef={robot}
    />

    {chatHidden && (
      <>
        <div className="avatar-pop">
          Cliquez sur <strong>Chat</strong> pour commencer une conversation 👋
        </div>

        <button
          className={
            'avatar-talk-btn ' +
            (listening ? 'listening ' : '') +
            (detecting ? 'detecting' : '')
          }
          onClick={toggleMic}
          title="Parler avec Izzy"
        >
          🎙
        </button>
      </>
    )}
  </div>

  {chatHidden && (
    <section className="home-panel">
      {/* <div className="home-kicker">Assistant intelligent Djezzy</div> */}
      <h1>Bienvenue, je suis Izzy.</h1>
      <p>Choisissez une recommandation ou ouvrez le chat pour poser votre propre question.</p>

      <div className="quick-actions">
        {recommendations.map(item => (
          <button
            key={item.label}
            className="quick-card"
            onClick={() => sendRecommendation(item.question)}
            disabled={busy}
          >
            {item.label}
          </button>
        ))}
      </div>

      <button className="open-chat-main" onClick={openChat}>
        💬 Ouvrir le chat
      </button>
    </section>
  )}
</main>

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

                {/* <button
                  className="sm-btn"
                  onClick={resetConversation}
                >
                  ↺ RESET
                </button> */}
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

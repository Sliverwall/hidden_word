const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = x => Math.round(x * 100);
let ws, S = null, uiKey = '', selected = null, tokenOn = false, curName = '', retry = null;
let detail = localStorage.getItem('hw_detail');
let cardsHidden = localStorage.getItem('hw_hide') === '1', lastMsg = Date.now(), lastHints = 0, lastView = '';
const MASK = '•••••';   // null = use server default

/* ── mobile: keep the shell exactly the visible height (keyboard-aware) ── */
function fit() { document.documentElement.style.setProperty('--app-h', (window.visualViewport ? visualViewport.height : innerHeight) + 'px'); }
fit(); addEventListener('resize', fit);
if (window.visualViewport) { visualViewport.addEventListener('resize', fit); visualViewport.addEventListener('scroll', () => scrollTo(0, 0)); }
let wl = null;
async function keepAwake() { try { wl = await navigator.wakeLock.request('screen'); } catch (e) {} }
addEventListener('focusout', () => setTimeout(fit, 150));
addEventListener('orientationchange', () => setTimeout(fit, 250));

/* Mobile browsers freeze sockets in the background without telling us, so the page can
   look alive while it is stale. Force a fresh connection on return, and heartbeat. */
function reconnectNow() {
  if (!S || !curName) return;
  const old = ws; try { old && old.close(); } catch (e) {}
  connect(curName);
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) { fit(); keepAwake(); reconnectNow(); } });
addEventListener('online', reconnectNow);
addEventListener('pageshow', e => { if (e.persisted) reconnectNow(); });
setInterval(() => {
  if (!S || !curName) return;
  if (ws && ws.readyState === 1) {
    const idle = Date.now() - lastMsg;
    if (idle > 8000) send({type: 'ping'});
    if (idle > 20000) reconnectNow();
  } else if (!retry) connect(curName);
}, 4000);

function connect(name) {
  curName = name; clearTimeout(retry); retry = null; lastMsg = Date.now();
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  const mine = ws;
  ws.onopen = () => send({type: 'join', name, session: localStorage.getItem('hw_session')});
  ws.onmessage = e => {
    lastMsg = Date.now();
    const m = JSON.parse(e.data);
    if (m.type === 'pong') return;
    if (m.type === 'joined') { localStorage.setItem('hw_session', m.pid); localStorage.setItem('hw_name', name); keepAwake(); }
    else if (m.type === 'state') { S = m.state; if ($('#toast').textContent.startsWith('Connection')) $('#toast').textContent = ''; $('#join').hidden = true; $('#game').hidden = false; render(); }
    else if (m.type === 'error') { $('#game').hidden ? ($('#join-err').textContent = m.message) : toast(m.message); }
    else if (m.type === 'suggest') showSuggest(m);
  };
  ws.onclose = e => {
    if (mine !== ws || e.code === 4000) { if (e.code === 4000) toast('Opened in another tab.'); return; }
    if (S) { toast('Connection lost. Reconnecting…'); retry = setTimeout(() => connect(name), 1500); }
  };
}
const send = o => ws && ws.readyState === 1 && ws.send(JSON.stringify(o));
function toast(t) { const el = $('#toast'); el.textContent = t; $('#dock').hidden = false;
  if (t) setTimeout(() => { if (el.textContent === t) { el.textContent = ''; renderDock(); } }, 4500); }

$('#join-btn').onclick = () => { const n = $('#name').value.trim(); if (n) connect(n); };
$('#name').onkeydown = e => { if (e.key === 'Enter') $('#join-btn').click(); };
$('#name').value = localStorage.getItem('hw_name') || '';
if (localStorage.getItem('hw_session') && localStorage.getItem('hw_name')) connect(localStorage.getItem('hw_name'));
$('#dbg').onclick = () => { detail = showDetail() ? '0' : '1'; localStorage.setItem('hw_detail', detail); render(); };
$('#hide').onclick = () => { cardsHidden = !cardsHidden; localStorage.setItem('hw_hide', cardsHidden ? '1' : '0'); if (S) render(); };
const showDetail = () => detail === null ? !!S.rules.show_breakdown : detail === '1';

const me = () => S.players.find(p => p.pid === S.you);
const giver = () => S.players.find(p => p.is_giver);
const iAmGiver = () => me().is_giver;

function render() {
  const r = S.rules, over = S.phase === 'game_over';
  $('#room').textContent = location.host;
  $('#roundinfo').textContent = S.phase === 'lobby' ? 'Lobby'
    : over ? 'Final' : `Round ${S.round}${r.max_rounds ? ' of ' + r.max_rounds : ''}${r.target_score ? '  First to ' + r.target_score : ''}`;
  $('#dbg').textContent = showDetail() ? 'Details on' : 'Details off';
  $('#dbg').setAttribute('aria-pressed', showDetail());
  $('#pills').innerHTML = S.players.map(p =>
    `<div class="pill ${p.is_giver ? 'giver' : ''} ${p.connected ? '' : 'off'}"><span>${esc(p.name)}</span>
     <span class="num">${p.score}</span><span class="tok">token ×${p.tokens}</span></div>`).join('');
  $('#stage').classList.toggle('over', over);
  $('#hide').textContent = cardsHidden ? 'Show cards' : 'Hide cards';
  $('#hide').setAttribute('aria-pressed', cardsHidden);
  const view = [S.phase, S.round, S.guess_round].join('|');          // new screen: start at the top
  if (view !== lastView) { lastView = view; $('#stage').scrollTop = 0; }
  renderStage(); renderDock();
}

function renderStage() {
  const g = giver(), B = $('#banner'), H = $('#hints'), F = $('#final'), R = $('#rounds'), ph = S.phase;
  H.hidden = F.hidden = true;
  if (ph === 'lobby') {
    B.innerHTML = `<h2>Waiting for players</h2><p class="muted">Others join on your Wi-Fi at <span class="mono">${esc(location.host)}</span></p>
      <p>${S.players.map(p => esc(p.name)).join(', ')}</p>
      ${S.host === S.you ? `<button class="primary block" id="start" ${S.players.length < 2 ? 'disabled' : ''}>Start game</button>` : '<p class="muted">The host will start the game.</p>'}`;
    const b = $('#start'); if (b) b.onclick = () => send({type: 'start'});
    R.hidden = true; return;
  }
  if (ph === 'selecting') {
    B.innerHTML = iAmGiver() ? `<h2>Choose your hidden word</h2><p class="muted">Tap one card from your hand.</p>`
      : `<h2>${esc(g.name)} is choosing a word</h2>`;
  } else if (ph === 'hinting') {
    const low = S.attempts_left <= 3 ? 'low' : '';
    B.innerHTML = iAmGiver()
      ? `<h2>Hint for <span class="mono">${cardsHidden ? MASK : esc(S.hidden)}</span></h2><p class="muted">Guess round ${S.guess_round} of ${S.rules.max_guess_rounds}. Reach ${pct(S.rules.threshold)}% to lock a hint. <span class="num ${low}">${S.attempts_left} attempts left</span></p>`
      : `<h2>${esc(g.name)} is thinking of a hint</h2><p class="muted">Guess round ${S.guess_round} of ${S.rules.max_guess_rounds}. <span class="num ${low}">${S.attempts_left} attempts left</span></p>`;
  } else if (ph === 'guessing') {
    const gs = S.players.filter(p => !p.is_giver);
    B.innerHTML = `<p class="muted">Locked hint, guess round ${S.guess_round} of ${S.rules.max_guess_rounds}</p><div class="locked">${esc(S.locked_hint)}</div>
      <p class="muted">Guessed: ${gs.filter(p => p.has_guessed).map(p => esc(p.name)).join(', ') || 'nobody yet'}</p>`;
  } else if (ph === 'turn_over') {
    const t = S.last_turn, pts = Object.entries(t.points).map(([n, v]) => `${esc(n)} +${v}`).join(', ') || 'No points scored';
    B.innerHTML = `<h2>${t.solved ? 'Word guessed' : 'Nobody got it'}</h2>
      <p>${esc(t.giver)}’s word was <strong class="mono ${t.solved ? 'ok' : ''}">${esc(t.hidden)}</strong></p>
      <p class="num">${pts}</p><button class="primary block" id="next">Next round</button>`;
    $('#next').onclick = () => send({type: 'next'});
  } else if (ph === 'game_over') {
    const t = S.last_turn;
    B.innerHTML = `<h2>Last word</h2><p>${esc(t.giver)}’s word was <strong class="mono ${t.solved ? 'ok' : ''}">${esc(t.hidden)}</strong>
      ${t.solved ? '' : '(nobody got it)'}</p>`;
    const sorted = S.players.slice().sort((a, b) => b.score - a.score);
    const w = S.winners.length > 1 ? `Tie: ${S.winners.map(esc).join(' and ')}` : `${esc(S.winners[0])} wins`;
    F.hidden = false;
    F.innerHTML = `<p class="muted">Game over</p><p class="big ok">${w}</p>
      <p class="muted">${S.end_reason === 'score' ? `Reached ${S.rules.target_score} points.` : 'Round limit reached.'}</p>` +
      sorted.map((p, i) => `<div class="final-row ${S.winners.includes(p.name) ? 'top' : ''}"><span class="rank num">${i + 1}</span>
        <span class="nm">${esc(p.name)}</span><span class="num">${p.score}</span></div>`).join('') +
      `<button class="primary block" id="again" style="margin-top:.75rem">Play again</button>
       <p class="muted">${esc((S.players[0] && nextOpener()) || '')}</p>`;
    $('#again').onclick = () => send({type: 'play_again'});
  }
  /* guess cards: every player's guesses for each resolved round, visible to everyone */
  R.hidden = !S.rounds_log.length;
  R.innerHTML = S.rounds_log.map(roundCard).join('');
  if (S.hints.length) { H.hidden = false; H.innerHTML = `<h2>Hints this turn</h2>` + S.hints.slice().reverse().map(hintRow).join(''); }
}
const nextOpener = () => '';   // rotation is handled by the server; nothing to preview

function roundCard(x) {
  const rows = Object.entries(x.guesses).map(([n, ws]) => {
    const ok = x.correct.includes(n);
    return `<div class="g"><span>${esc(n)}</span><span class="${ok ? 'ok' : ''}">${ws.map(esc).join(', ')}${ok ? ' ✓' : ''}</span></div>`;
  }).join('');
  return `<article class="rcard"><div class="rh"><span class="muted">Guess round ${x.round}</span><strong>${esc(x.hint)}</strong></div>${rows}</article>`;
}

function hintRow(h) {
  const hit = h.score >= S.rules.threshold;
  return `<div class="hint-row ${hit ? 'hit' : ''}"><div class="hint-top"><strong>${esc(h.word)}</strong>
    <span class="num pct">${pct(h.score)}%</span></div>
    <div class="bar"><div class="fill" style="width:${pct(h.score)}%"></div><div class="mark" style="left:${pct(S.rules.threshold)}%"></div></div>
    <div class="sub num">${showDetail() ? `<span>meaning ${pct(h.sem)}%</span><span>association ${pct(h.assoc)}%</span>` : ''}
    ${h.fallback ? '<span class="tag">closest word in the bank</span>' : ''}</div></div>`;
}

/* ── dock: hand + inputs, rebuilt only when the interaction context changes ── */
function renderDock() {
  const ph = S.phase, m = me(), D = $('#dock');
  const active = ['selecting', 'hinting', 'guessing'].includes(ph);
  D.hidden = !active && !$('#toast').textContent;
  if (!active) { uiKey = ''; $('#hand').innerHTML = ''; $('#hand').dataset.html = ''; $('#action').innerHTML = ''; return; }
  if (selected && !S.hand.includes(selected)) selected = null;     // card was replaced
  if (ph !== 'selecting') selected = null;
  const pickable = ph === 'selecting' && iAmGiver();
  const hand = $('#hand');
  const html = S.hand.map(w => `<button class="card ${cardsHidden ? 'masked' : ''} ${w === selected && pickable ? 'sel' : ''} ${w === S.hidden ? 'hidden-word' : ''}"
    data-w="${esc(w)}" ${pickable ? '' : 'disabled'}>${cardsHidden ? MASK : esc(w)}</button>`).join('');
  if (hand.dataset.html !== html) {                                // keep scroll position otherwise
    hand.dataset.html = html; hand.innerHTML = html;
    hand.querySelectorAll('.card').forEach(c => c.onclick = () => { selected = c.dataset.w; renderDock(); });
  }

  const key = [ph, S.round, S.guess_round, iAmGiver(), ph === 'guessing' && m.has_guessed].join('|');
  if (key === uiKey && ph !== 'selecting') {
    if (ph === 'hinting' && iAmGiver() && S.hints.length !== lastHints) {   // last hint went through
      lastHints = S.hints.length; const hi = $('#hint'); if (hi) hi.value = ''; const sg = $('#sug'); if (sg) sg.innerHTML = '';
    }
    return;
  }
  uiKey = key; lastHints = S.hints.length;
  const A = $('#action'); A.innerHTML = '';
  if (ph === 'selecting') {
    if (!iAmGiver()) return;
    A.innerHTML = `<button class="primary block" id="pick" ${selected ? '' : 'disabled'}>${selected ? (cardsHidden ? 'Use selected card' : `Use “${esc(selected)}”`) : 'Select a card'}</button>`;
    $('#pick').onclick = () => send({type: 'select', word: selected});
    uiKey = '';
  } else if (ph === 'hinting' && iAmGiver()) {
    A.innerHTML = `<div class="row"><input id="hint" placeholder="Type a hint" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="true" enterkeyhint="send">
      <button class="primary" id="hint-go">Send</button></div><div id="sug"></div><p class="muted" style="font-size:.8rem">Start with a capital letter for names (Paris).</p>`;
    const go = confirmed => { $('#sug').innerHTML = ''; send({type: 'hint', word: $('#hint').value, confirmed}); };
    $('#hint').oninput = () => { $('#sug').innerHTML = ''; };
    $('#hint-go').onclick = () => go(false);
    $('#hint').onkeydown = e => { if (e.key === 'Enter') go(false); };
    window.pendingConfirm = () => go(true);
  } else if (ph === 'guessing' && !iAmGiver()) {
    if (m.has_guessed) { A.innerHTML = '<p class="muted">Guess locked in. Waiting for the others.</p>'; return; }
    tokenOn = false;
    const n = S.rules.extra_guesses;
    A.innerHTML = `<div class="row"><input id="g1" placeholder="Your guess" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="true" enterkeyhint="send">
      <button class="primary" id="g-go">Guess</button></div>
      <div id="guess2-wrap"><input id="g2" placeholder="Second guess" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="true"></div>
      <div class="row" style="margin-top:.5rem"><button class="token" id="tok" aria-pressed="false" ${m.tokens > 0 ? '' : 'disabled'}>Use Extra Word Token (${n} guesses)</button>
      <span class="muted num">×${m.tokens}</span></div><div id="sug"></div>`;
    $('#tok').onclick = () => { tokenOn = !tokenOn; $('#tok').setAttribute('aria-pressed', tokenOn); $('#guess2-wrap').classList.toggle('open', tokenOn); };
    const go = confirmed => { $('#sug').innerHTML = ''; send({type: 'guess', use_token: tokenOn, confirmed,
      words: tokenOn ? [$('#g1').value, $('#g2').value] : [$('#g1').value]}); };
    A.querySelectorAll('input').forEach(i => i.oninput = () => { $('#sug').innerHTML = ''; });
    $('#g-go').onclick = () => go(false);
    A.querySelectorAll('input').forEach(i => i.onkeydown = e => { if (e.key === 'Enter') go(false); });
    window.pendingConfirm = () => go(true);
  } else if (ph === 'guessing') {
    A.innerHTML = '<p class="muted">Waiting for guesses.</p>';
  } else if (ph === 'hinting') {
    A.innerHTML = '<p class="muted">Waiting for the next hint.</p>';
  }
}

function showSuggest(m) {
  const box = $('#sug'); if (!box) return;
  box.innerHTML = `<div class="suggest"><div>Did you mean:</div>` + m.suggest.map(it =>
    `<div class="chips" data-i="${it.index}"><span class="muted">“${esc(it.original)}”</span>${it.suggestions.map(s =>
      `<button class="chip" data-s="${esc(s)}">${esc(s)}</button>`).join('')}</div>`).join('') +
    `<button id="keep">Keep as typed</button></div>`;
  const inputs = m.context === 'hint' ? [$('#hint')] : [$('#g1'), $('#g2')];
  box.querySelectorAll('.chip').forEach(c => c.onclick = () => {
    const grp = c.parentElement; inputs[+grp.dataset.i].value = c.dataset.s; grp.remove();
    if (!box.querySelector('.chips')) { box.innerHTML = ''; (m.context === 'hint' ? $('#hint-go') : $('#g-go')).click(); }
  });
  $('#keep').onclick = () => { box.innerHTML = ''; window.pendingConfirm(); };
  box.scrollIntoView({block: 'nearest'});
}

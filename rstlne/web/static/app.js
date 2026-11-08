"use strict";
// rstlne in the browser. The server runs the game; this page draws what it sends and sends the human's
// commands, in the same words the terminal takes ("s", "v E", "solve ...", "T", "keep", "B G H I").

const $ = (sel) => document.querySelector(sel);
const VOWELS = new Set("AEIOU");
const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const KIND_NAMES = { human: "You", bot: "Bot", llm: "Model", hybrid: "Hybrid (bot + model)", decision: "Decision seat" };
const SAVED = "rstlne.setup";

let setupInfo = null;
let ws = null;
let gameId = null;
let seats = [];          // from the start event: label, kind, you
let me = null;           // the human's seat, or null when watching
let table = null;        // the latest public view
let prompt = null;       // the human's open prompt
let thoughts = {};       // seat -> lines, when watching
let lastShown = new Set();
let replaying = false, replayTimer = null;
let wheelSignature = "", wheelAngle = 0;
let clockTimer = null;
let over = false;
let seed = null;

const short = (label) => (label.includes("/") ? label.split("/").pop() : label);
const money = (n) => "$" + Number(n).toLocaleString("en-US");
const store = {
  get() { try { return JSON.parse(localStorage.getItem(SAVED)); } catch { return null; } },
  set(v) { try { localStorage.setItem(SAVED, JSON.stringify(v)); } catch { /* private window */ } },
};

// ---------- Setup ----------

async function showSetup(error) {
  over = false;
  $("#game").hidden = true; $("#over").hidden = true; $("#setup").hidden = false;
  $("#status").textContent = "";
  if (!setupInfo) setupInfo = await (await fetch("/api/setup")).json();
  const saved = store.get() || ["human", "bot", "bot"];
  const pickers = $("#pickers");
  pickers.innerHTML = "";
  saved.forEach((seat, i) => pickers.appendChild(picker(i, seat)));
  $("#setup-error").textContent = error || "";
}

function picker(i, seat) {
  const [kind, ...rest] = seat.split(":");
  const model = rest.join(":");
  const box = document.createElement("div");
  box.className = "picker";
  box.innerHTML = `<h3>Seat ${i + 1}</h3>
    <select class="kind" aria-label="Seat ${i + 1} plays as">
      ${Object.entries(KIND_NAMES).map(([k, name]) => `<option value="${k}">${name}</option>`).join("")}
    </select>
    <select class="model" aria-label="Seat ${i + 1} model"></select>
    <input class="other" placeholder="any OpenRouter slug, like openai/gpt-6-luna" hidden>`;
  const kindSel = box.querySelector(".kind"), modelSel = box.querySelector(".model"), other = box.querySelector(".other");
  kindSel.value = KIND_NAMES[kind] ? kind : "bot";
  const fill = () => {
    const k = kindSel.value;
    const list = k === "llm" ? setupInfo.models : k === "hybrid" ? setupInfo.hybrid_models : k === "decision" ? setupInfo.decision_models : [];
    modelSel.hidden = list.length === 0 && k !== "llm";
    modelSel.innerHTML = list.map((m) => `<option value="${m}">${m}</option>`).join("") + (k === "llm" ? `<option value="__other">another model…</option>` : "");
    if (list.includes(model)) modelSel.value = model;
    else if (k === "llm" && model) { modelSel.value = "__other"; other.value = model; }
    other.hidden = modelSel.value !== "__other" || modelSel.hidden;
  };
  kindSel.onchange = fill;
  modelSel.onchange = () => { other.hidden = modelSel.value !== "__other"; };
  fill();
  return box;
}

function chosenSeats() {
  return [...document.querySelectorAll(".picker")].map((box) => {
    const kind = box.querySelector(".kind").value;
    const modelSel = box.querySelector(".model");
    if (kind === "human" || kind === "bot") return kind;
    const model = modelSel.value === "__other" ? box.querySelector(".other").value.trim() : modelSel.value;
    return model ? `${kind}:${model}` : kind;
  });
}

async function startGame() {
  const chosen = chosenSeats();
  if (chosen.filter((s) => s === "human").length > 1) {
    $("#setup-error").textContent = "Only one seat can be you.";
    return;
  }
  store.set(chosen);
  const seedText = $("#seed").value.trim();
  const body = { seats: chosen };
  if (seedText) body.seed = Number(seedText);
  $("#start").disabled = true;
  try {
    const r = await fetch("/api/games", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json();
    if (!r.ok) { $("#setup-error").textContent = data.detail || "The game couldn't start."; return; }
    location.hash = "g=" + data.id;
    connect(data.id);
  } finally {
    $("#start").disabled = false;
  }
}

// ---------- Connection ----------

function connect(id) {
  gameId = id;
  table = null; prompt = null; thoughts = {}; lastShown = new Set(); over = false;
  $("#moves").innerHTML = ""; $("#thinking").innerHTML = ""; $("#banner").hidden = true;
  $("#setup").hidden = true; $("#over").hidden = true; $("#game").hidden = false;
  replaying = true;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/api/games/${id}`);
  ws.onmessage = (e) => {
    clearTimeout(replayTimer);
    replayTimer = setTimeout(() => { replaying = false; }, 250);  // the history arrives in a burst
    enqueue(JSON.parse(e.data));
  };
  ws.onclose = () => { if (!over) $("#status").textContent += " · disconnected"; };
}

function send(command) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ command }));
  prompt = null;
  renderControls();
}

// Events play one at a time. A spin holds the ones after it until the wheel stops, so the next seat's
// highlight, the wedge's result, and the human's controls wait for the wheel.
const SPIN_MS = 1700;
const pending = [];
let draining = false;
const pause = (ms) => new Promise((done) => setTimeout(done, ms));

function enqueue(ev) {
  pending.push(ev);
  if (!draining) drain();
}

async function drain() {
  draining = true;
  while (pending.length) {
    const wait = handle(pending.shift());
    if (wait && !replaying) await pause(wait);
  }
  draining = false;
}

function handle(ev) {
  switch (ev.type) {
    case "start":
      seats = ev.seats;
      me = seats.findIndex((s) => s.you);
      if (me < 0) me = null;
      $("#thinking-panel").hidden = me !== null;  // a seat's thinking would give its best guess away
      seed = ev.seed;
      $("#status").textContent = `seed ${seed}`;
      break;
    case "round":
      $("#round-line").textContent = ev.round ? `Round ${ev.round}` : "Bonus round";
      $("#status").textContent = `${ev.round ? "Round " + ev.round : "Bonus round"} · seed ${seed}`;
      addMove(ev.round ? `Round ${ev.round}: ${seatName(ev.starts)} ${ev.starts === me ? "start" : "starts"}.` : `Bonus round: ${seatName(ev.starts)} ${ev.starts === me ? "play" : "plays"} for an envelope.`, null, "big");
      lastShown = new Set();
      break;
    case "table":
      table = ev;
      $("#banner").hidden = true;
      renderTable();
      break;
    case "move":
      prompt = null;
      renderControls();
      if (ev.wedge && !replaying) {  // the wheel turns first; its result shows once it stops
        spinTo(ev.wedge);
        pending.unshift({ type: "landed", text: ev.text, note: ev.note });
        return SPIN_MS;
      }
      if (ev.wedge) spinTo(ev.wedge);
      addMove(ev.text, ev.note, ev.outcome === "solved" || ev.outcome === "bonus_solved" ? "big" : "");
      break;
    case "landed":
      addMove(ev.text, ev.note, "");
      break;
    case "thoughts":
      thoughts[ev.seat] = ev.lines;
      renderThoughts();
      break;
    case "solved":
      drawBoard(ev.rows, true);
      $("#category").textContent = ev.category;
      showBanner(lastMoveText());
      break;
    case "round_over":
      addMove(ev.text, null, "big");
      break;
    case "prompt":
      prompt = ev;
      renderControls();
      break;
    case "over":
      over = true;
      renderOver(ev);
      break;
    case "failed":
      over = true;
      if (!table) { location.hash = ""; showSetup(ev.text); return; }
      $("#controls").innerHTML = `<div class="error">${escapeHtml(ev.text)}</div>`;
      break;
  }
}

// ---------- Drawing the table ----------

function seatName(i) {
  if (i === me) return "You";
  return `Seat ${i + 1}`;
}

function renderTable() {
  const t = table;
  if (t.round) $("#round-line").textContent = `Round ${t.round}`;
  drawBoard(t.rows, false);
  $("#category").textContent = t.category;
  drawLetters(new Set(t.used));
  drawWheel(t.wheel);
  $("#wheel-wrap").hidden = !t.wheel.length;
  $("#wedge-line").textContent = t.express ? "Riding the Express" : t.wedge ? `Wedge: ${t.wedge.text}` : "";
  drawSeats();
  renderControls();
}

function drawBoard(rows, solved) {
  const board = $("#board");
  board.innerHTML = "";
  const shown = new Set();
  rows.forEach((row, r) => {
    const line = document.createElement("div");
    line.className = "row";
    row.forEach((ch, c) => {
      const tile = document.createElement("div");
      const key = `${r}:${c}`;
      if (ch === " ") tile.className = "tile gap";
      else if (ch === "_") tile.className = "tile hidden";
      else {
        tile.className = "tile shown";
        tile.textContent = ch;
        shown.add(key);
        if (!replaying && !lastShown.has(key) && lastShown.size + (solved ? 1 : 0) > 0) tile.classList.add("fresh");
      }
      line.appendChild(tile);
    });
    board.appendChild(line);
  });
  lastShown = shown;
}

function drawLetters(used) {
  $("#letters").innerHTML = [...ALPHABET].map((c) =>
    `<span class="letter${VOWELS.has(c) ? " vowel" : ""}${used.has(c) ? " used" : ""}" aria-label="${c}${used.has(c) ? " used" : ""}">${c}</span>`).join("");
}

function drawSeats() {
  const t = table;
  $("#seats").innerHTML = t.seats.map((label, i) => {
    const kind = seats[i] ? seats[i].kind : "";
    const cards = [t.wild[i] ? `<span class="card">Wild Card</span>` : "", t.million[i] ? `<span class="card">Million</span>` : ""].join("");
    return `<div class="seat${t.turn === i && t.phase !== "game_over" ? " turn" : ""}">
      <div class="who">Seat ${i + 1} · <b>${escapeHtml(i === me ? "You" : short(label))}</b>${["llm", "hybrid", "decision"].includes(kind) && i !== me ? ` <span class="kind">(${kind === "llm" ? "model" : kind})</span>` : ""}</div>
      <div class="bank">${money(t.banks[i])}</div>
      <div class="total">Total ${money(t.totals[i])}</div>
      <div class="cards">${cards}</div>
    </div>`;
  }).join("");
}

function renderThoughts() {
  if (me !== null) return;
  $("#thinking").innerHTML = Object.keys(thoughts).sort().map((s) =>
    `<div class="think"><b>Seat ${Number(s) + 1} · ${escapeHtml(short(seats[s] ? seats[s].label : ""))}</b>${thoughts[s].map((l) => `<p>${escapeHtml(l)}</p>`).join("")}</div>`).join("");
}

function addMove(text, note, cls) {
  const li = document.createElement("li");
  if (cls) li.className = cls;
  li.textContent = text;
  if (note) { const n = document.createElement("span"); n.className = "note"; n.textContent = note; li.appendChild(n); }
  $("#moves").prepend(li);
}

function lastMoveText() {
  const first = $("#moves li");
  return first ? first.firstChild.textContent : "";
}

function showBanner(text) {
  const b = $("#banner");
  b.textContent = text;
  b.hidden = !text;
}

// ---------- The wheel ----------

const CASH_TONES = ["--w-cash-1", "--w-cash-2", "--w-cash-3", "--w-cash-4", "--w-cash-5", "--w-cash-6"];

function wedgeFill(w) {
  switch (w.kind) {
    case "bankrupt": return "var(--w-bankrupt)";
    case "lose_a_turn": return "var(--w-lose)";
    case "free_play": return "var(--w-free)";
    case "mystery": return "var(--w-mystery)";
    case "express": return "var(--w-express)";
    case "million": return "var(--w-million)";
    default: return `var(${CASH_TONES[(w.number - 1) % CASH_TONES.length]})`;
  }
}

function wedgeLabel(w) {
  switch (w.kind) {
    case "bankrupt": return "BANKRUPT";
    case "lose_a_turn": return "LOSE A TURN";
    case "free_play": return "FREE PLAY";
    case "mystery": return "MYSTERY";
    case "express": return "EXPRESS";
    case "million": return "MILLION";
    default: return `${w.value}`;
  }
}

const point = (r, deg) => [r * Math.sin(deg * Math.PI / 180), -r * Math.cos(deg * Math.PI / 180)];

function drawWheel(thirds) {
  if (!thirds.length) return;
  const signature = JSON.stringify(thirds.map((w) => [w.kind, w.value, w.wild]));
  if (signature === wheelSignature) return;
  wheelSignature = signature;
  const g = $("#wheel-rot");
  let svg = "";
  thirds.forEach((w, i) => {
    const a1 = i * 5, a2 = a1 + 5;
    const [x1, y1] = point(100, a1), [x2, y2] = point(100, a2);
    const light = w.kind === "lose_a_turn";
    svg += `<path d="M0 0 L${x1.toFixed(2)} ${y1.toFixed(2)} A100 100 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z" fill="${wedgeFill(w)}" stroke="${light ? "var(--line)" : "none"}" stroke-width=".4"/>`;
  });
  for (let k = 0; k < thirds.length / 3; k++) {  // a line between wedges, and a label on each
    const [x, y] = point(100, k * 15);
    svg += `<line x1="0" y1="0" x2="${x.toFixed(2)}" y2="${y.toFixed(2)}" stroke="var(--surface)" stroke-width=".8"/>`;
    const mid = thirds[k * 3 + 1];
    const dark = ["bankrupt", "free_play", "mystery", "express"].includes(mid.kind);
    const text = wedgeLabel(mid);
    const size = text.length > 6 ? 5.2 : 7.5;
    svg += `<text transform="rotate(${k * 15 + 7.5}) translate(0 -92) rotate(90)" font-size="${size}" text-anchor="start" dominant-baseline="middle" fill="${dark ? "#fff" : "#1d1b18"}">${text}${mid.wild ? " ★" : ""}</text>`;
  }
  g.innerHTML = svg;
  g.style.transform = `rotate(${wheelAngle}deg)`;
}

function spinTo(wedge) {
  if (!table || !table.wheel.length) return;
  const thirds = table.wheel;
  const base = (wedge.number - 1) * 3;
  const options = [0, 1, 2].filter((k) => thirds[base + k] && thirds[base + k].kind === wedge.kind);
  const k = options.includes(1) ? 1 : options.length ? options[Math.floor(Math.random() * options.length)] : 1;
  const center = (base + k) * 5 + 2.5;
  const target = ((-center - wheelAngle) % 360 + 360) % 360;
  wheelAngle += (replaying ? 0 : 720) + target;
  const g = $("#wheel-rot");
  g.classList.toggle("spinning", !replaying);
  g.style.transform = `rotate(${wheelAngle}deg)`;
  $("#wedge-line").textContent = replaying ? `Wedge: ${wedge.text}` : "Spinning…";
}

// ---------- The human's controls ----------

function renderControls() {
  const box = $("#controls");
  clearInterval(clockTimer);
  if (over) { box.innerHTML = ""; return; }
  if (!prompt || prompt.seat !== me) {
    const turn = table ? table.turn : null;
    box.innerHTML = turn === null ? "" : `<div class="waiting">${turn === me ? "Your move…" : `${seatName(turn)} (${escapeHtml(short(table.seats[turn]))}) is up.`}</div>`;
    return;
  }
  const p = prompt;
  const used = new Set(table ? table.used : []);
  const legal = new Set(p.legal);
  let html = p.error ? `<div class="error">${escapeHtml(p.error)}</div>` : "";
  const keys = (letters, cmd, cls = "") => `<div class="keys">${[...letters].map((c) =>
    `<button class="key${VOWELS.has(c) ? " vowel" : ""} ${cls}" data-cmd="${cmd(c)}" ${used.has(c) ? "disabled" : ""} aria-label="${c}">${c}</button>`).join("")}</div>`;
  const consonants = [...ALPHABET].filter((c) => !VOWELS.has(c)).join("");

  switch (p.phase) {
    case "turn":
    case "express":
      html += `<div class="actions">
        ${legal.has("spin") ? `<button class="primary" data-cmd="s">Spin</button>` : ""}
        ${p.phase === "express" ? `<span class="label">Riding the Express: call a consonant, buy a vowel, or solve.</span>` : ""}
      </div>`;
      if (p.phase === "express" && legal.has("call_consonant")) html += keys(consonants, (c) => c);
      if (legal.has("buy_vowel")) html += `<div class="actions"><span class="label">Buy a vowel ($250):</span>${keys("AEIOU", (c) => `v ${c}`)}</div>`;
      if (legal.has("solve")) html += solveBox("Solve", (text) => `solve ${text}`);
      break;
    case "call_consonant":
    case "wild_consonant":
      html += `<div class="label">${p.phase === "wild_consonant" ? "Call your extra consonant." : "Call a consonant."}</div>` + keys(consonants, (c) => c);
      break;
    case "free_play":
      html += `<div class="label">Free Play: call any letter. A vowel is free, and a miss keeps your turn.</div>` + keys(ALPHABET, (c) => c);
      break;
    case "mystery_choice":
      html += `<div class="actions"><span class="label">Keep the money, or flip the wedge: $10,000 or Bankrupt.</span>
        <button data-cmd="keep">Keep</button><button class="primary" data-cmd="flip">Flip</button></div>`;
      break;
    case "express_choice":
      html += `<div class="actions"><span class="label">Ride the Express? Any miss or wrong solve is Bankrupt.</span>
        <button data-cmd="pass">Pass</button><button class="primary" data-cmd="play">Ride</button></div>`;
      break;
    case "wild_choice":
      html += `<div class="actions"><span class="label">Spend the Wild Card on one more consonant at this value?</span>
        <button data-cmd="no">Keep the card</button><button class="primary" data-cmd="wild">Spend it</button></div>`;
      break;
    case "bonus_picks":
      html += picksBox(p.bonus_consonants || 3, used);
      break;
    case "bonus_solve":
      html += `<div class="clock"><div id="clock-bar"></div></div>` + solveBox("Answer", (text) => text, true);
      break;
  }
  box.innerHTML = html;
  box.querySelectorAll("[data-cmd]").forEach((b) => { b.onclick = () => send(b.dataset.cmd); });
  wireSolve(box);
  wirePicks(box, p.bonus_consonants || 3);
  if (p.phase === "bonus_solve") startClock(p.seconds);
}

function solveBox(label, toCommand, focus = false) {
  solveBox.toCommand = toCommand;
  return `<form class="solve" data-solve>
    <input name="answer" placeholder="Type the whole answer" autocomplete="off" aria-label="Your answer" ${focus ? "autofocus" : ""}>
    <button class="primary" type="submit">${label}</button></form>`;
}

function wireSolve(box) {
  const form = box.querySelector("[data-solve]");
  if (!form) return;
  form.onsubmit = (e) => {
    e.preventDefault();
    const text = form.answer.value.trim();
    if (text || prompt?.phase === "bonus_solve") send(solveBox.toCommand(text || " "));
  };
  if (prompt?.phase === "bonus_solve") form.answer.focus();
}

function picksBox(n, used) {
  const letters = [...ALPHABET].filter((c) => !used.has(c));
  return `<div class="label">Pick ${n} consonants and 1 vowel. R S T L N E are already up.</div>
    <div class="keys" data-picks>${letters.map((c) => `<button class="key${VOWELS.has(c) ? " vowel" : ""}" data-pick="${c}">${c}</button>`).join("")}</div>
    <div class="actions"><button class="primary" data-picks-go disabled>Reveal</button><span class="label" data-picks-left></span></div>`;
}

function wirePicks(box, n) {
  const keysBox = box.querySelector("[data-picks]");
  if (!keysBox) return;
  const chosen = new Set();
  const go = box.querySelector("[data-picks-go]"), left = box.querySelector("[data-picks-left]");
  const update = () => {
    const c = [...chosen].filter((x) => !VOWELS.has(x)).length, v = [...chosen].filter((x) => VOWELS.has(x)).length;
    go.disabled = !(c === n && v === 1);
    left.textContent = `${c} of ${n} consonants, ${v} of 1 vowel`;
  };
  keysBox.querySelectorAll("[data-pick]").forEach((b) => {
    b.onclick = () => {
      const c = b.dataset.pick, vowel = VOWELS.has(c);
      if (chosen.has(c)) chosen.delete(c);
      else {
        const same = [...chosen].filter((x) => VOWELS.has(x) === vowel);
        if (same.length >= (vowel ? 1 : n)) chosen.delete(same[0]);
        chosen.add(c);
      }
      keysBox.querySelectorAll("[data-pick]").forEach((k) => k.classList.toggle("on", chosen.has(k.dataset.pick)));
      update();
    };
  });
  go.onclick = () => send([...chosen].join(" "));
  update();
}

function startClock(seconds) {
  const bar = $("#clock-bar");
  if (!bar || !seconds) return;
  const end = performance.now() + seconds * 1000;
  clockTimer = setInterval(() => {
    const left = Math.max(0, end - performance.now());
    bar.style.width = `${(left / (seconds * 1000)) * 100}%`;
    if (!left) clearInterval(clockTimer);
  }, 50);
}

document.addEventListener("keydown", (e) => {
  if (!prompt || prompt.seat !== me || e.target.closest("input, select, textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
  const c = e.key.toUpperCase();
  if (c.length !== 1 || !ALPHABET.includes(c) || (table && table.used.includes(c))) return;
  const phase = prompt.phase;
  if (((phase === "call_consonant" || phase === "wild_consonant") && !VOWELS.has(c)) || phase === "free_play"
      || (phase === "express" && !VOWELS.has(c) && prompt.legal.includes("call_consonant"))) {
    e.preventDefault();
    send(c);
  } else if (phase === "turn" && c === "S" && prompt.legal.includes("spin")) {
    e.preventDefault();
    send("s");
  }
});

// ---------- The result ----------

function renderOver(ev) {
  $("#game").hidden = true;
  const box = $("#over");
  box.hidden = false;
  const totals = ev.totals, best = Math.max(...totals);
  const b = ev.bonus;
  const rows = b ? b.rows.map((row) => `<div class="row">${row.map((ch) => ch === " " ? `<div class="tile gap"></div>` : `<div class="tile shown">${ch}</div>`).join("")}</div>`).join("") : "";
  box.innerHTML = `
    <h1>${winnerLine(totals)}</h1>
    ${b ? `<div class="board-wrap"><div class="round-line">Bonus round · ${escapeHtml(b.category)}</div><div class="board">${rows}</div>
      <div class="category">${seatName(b.seat)} ${b.solved ? "solved it" : "missed it"}. The envelope held ${b.envelope_text}.</div></div>` : ""}
    <table class="totals"><thead><tr><th>Seat</th><th class="num">Before the bonus</th><th class="num">Final total</th></tr></thead>
      <tbody>${totals.map((t, i) => `<tr class="${t === best ? "winner" : ""}"><td>Seat ${i + 1} · ${escapeHtml(i === me ? "You" : short(seats[i] ? seats[i].label : ""))}</td>
        <td class="num">${money(ev.before_bonus[i])}</td><td class="num">${money(t)}</td></tr>`).join("")}</tbody></table>
    ${ev.usage.length ? `<div class="usage">${ev.usage.map((u) => `${escapeHtml(u.model)}: ${u.calls} calls, ${u.tokens.toLocaleString()} tokens (${u.cached.toLocaleString()} from cache), $${u.cost.toFixed(4)}`).join("<br>")}</div>` : ""}
    <div class="usage">Log: <code>${escapeHtml(ev.log)}</code></div>
    <div class="actions"><button class="primary" id="again">New game</button></div>`;
  $("#again").onclick = newGame;
  $("#status").textContent = "Game over";
}

function winnerLine(totals) {
  const best = Math.max(...totals);
  const winners = totals.map((t, i) => (t === best ? i : -1)).filter((i) => i >= 0);
  if (winners.length > 1) return `A tie at ${money(best)}`;
  return winners[0] === me ? `You won with ${money(best)}!` : `${seatName(winners[0])} won with ${money(best)}`;
}

async function newGame() {
  if (gameId) { fetch(`/api/games/${gameId}`, { method: "DELETE" }).catch(() => {}); }
  if (ws) ws.close();
  gameId = null;
  history.replaceState(null, "", location.pathname);
  showSetup();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------- Start ----------

$("#start").onclick = startGame;
$(".brand").onclick = (e) => { e.preventDefault(); newGame(); };
const hashed = location.hash.match(/g=([0-9a-f]+)/);
if (hashed) connect(hashed[1]); else showSetup();

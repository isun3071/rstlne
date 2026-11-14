"use strict";
// rstlne in the browser. The server runs the game; this page draws what it sends and sends the human's
// commands, in the same words the terminal takes ("s", "v E", "solve ...", "T", "keep", "B G H I").
// Replays draw a logged game's events the same way, one move at a time.

const $ = (sel) => document.querySelector(sel);
const VOWELS = new Set("AEIOU");
const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const CONSONANTS = [...ALPHABET].filter((c) => !VOWELS.has(c)).join("");
const KIND_NAMES = { human: "Human", bot: "Bot", llm: "Model", hybrid: "Hybrid (bot + model)", decision: "Decision seat" };
const SAVED = "rstlne.setup", NAMES_SAVED = "rstlne.names", STOPS_SAVED = "rstlne.stops";
const SPIN_MS = 1700;
const LANDED_MS = 1200;
const CALL_MS = 1100;  // a bot's or model's letter shows big over the board this long before the tiles turn
const LETTER_KINDS = new Set(["call_consonant", "call_letter", "buy_vowel"]);
const SOLVE_LEAD_MS = 1000;  // the board as it stands, before a bot's or model's answer covers it
const SOLVE_MS = 1500;  // a bot's or model's answer shows on the board this long before it's judged
const SOLVE_KINDS = new Set(["solve", "bonus_solve"]);
const GAP_MS = 900;      // at least this long between two moves by bots or models, so each can be read
const MISS_MS = 900;     // a letter that isn't there, a wrong answer, or a choice's outcome holds this long
const CHOICE_MS = 1200;  // a special wedge choice or bonus picks show this long before they play out
const ROUND_MS = 2600;   // a new round's card
const SOLVED_MS = 5000;
const SOURCE_MS = 8000;  // the same, when the puzzle's source shows under it
const BONUS_EMPTY_MS = 1800;  // the bonus board, empty, before its wheel spins
const BONUS_FREE_MS = 1600;   // R S T L N E announced
const BONUS_LIT_MS = 1600;    // R S T L N E lit on the board before the picks  // a solved board holds this long, its banner up, before the next round's card
const ROUND_START_MS = 700;  // and the new round's board shows this much longer than the usual gap before its first move
const OVER_MS = 3000;    // the last result holds this long before the final scores
let lastMoveAt = 0;
const staged = (seat) => mode === "replay" || !humans.includes(seat);  // a bot's or model's move, or any move in a replay  // after a bot's or model's spin lands, a beat to read the wedge before its next move

let setupInfo = null;
let mode = "play";       // "play" a live game, or "replay" a log
let ws = null, gameId = null;
let seats = [], humans = [], me = null, table = null, prompt = null, thoughts = {};
let lastShown = new Set(), replaying = false, replayTimer = null;
let wheelSignature = "", wheelAngle = 0, clockTimer = null, over = false, seed = null;
let roundList = null;
let thinkingSeat = null;  // the bot or model the server says is about to move
let bonusSpun = false;
let bonusRevealed = false;   // the bonus wheel turns once, when the bonus round starts    // the <ol> the next move goes into
let rp = null;           // the replay: meta, groups of events, position, playing, speed, stops

const short = (label) => String(label).split(" + ").map((p) => (p.includes("/") ? p.split("/").pop() : p)).join(" + ");
const money = (n) => "$" + Number(n).toLocaleString("en-US");
const pause = (ms) => new Promise((done) => setTimeout(done, ms));
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const store = {
  get(key, fallback) { try { const v = JSON.parse(localStorage.getItem(key)); return v ?? fallback; } catch { return fallback; } },
  set(key, v) { try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* private window */ } },
};

function show(view) {
  for (const id of ["setup", "replays", "game", "over"]) $("#" + id).hidden = id !== view;
  const onReplays = view === "replays" || (mode === "replay" && view !== "setup");
  for (const [id, on] of [["#nav-play", !onReplays], ["#nav-replays", onReplays]]) {
    if (on) $(id).setAttribute("aria-current", "page"); else $(id).removeAttribute("aria-current");
  }
}

// ---------- Setup ----------

async function showSetup(error) {
  leave();
  show("setup");
  $("#status").textContent = "";
  if (!setupInfo) setupInfo = await (await fetch("/api/setup")).json();
  drawPickers(store.get(SAVED, ["human", "bot", "bot"]), store.get(NAMES_SAVED, [null, null, null]));
  $("#setup-error").textContent = error || "";
}

function drawPickers(chosen, names = []) {
  const pickers = $("#pickers");
  pickers.innerHTML = "";
  chosen.forEach((seat, i) => pickers.appendChild(picker(i, seat, names[i] || "")));
}

function picker(i, seat, name = "") {
  const [kind, ...rest] = seat.split(":");
  const [named, solver = ""] = rest.join(":").split("@");  // a decision seat may name its solver: decision:<model>@<solver>
  const [model, variant = ""] = named.split("+");  // a hybrid seat may name a variant: hybrid:<model>+trust_fit
  const box = document.createElement("div");
  box.className = "picker";
  box.innerHTML = `<h3>Seat ${i + 1}</h3>
    <select class="kind" aria-label="Seat ${i + 1} plays as">
      ${Object.entries(KIND_NAMES).map(([k, name]) => `<option value="${k}">${name}</option>`).join("")}
    </select>
    <select class="model" aria-label="Seat ${i + 1} model"></select>
    <select class="solver" aria-label="Seat ${i + 1} solver" hidden></select>
    <select class="strategy" aria-label="Seat ${i + 1} strategy" hidden>
      <option value="">plays its standard strategy</option>
      ${Object.entries(setupInfo.bot_strategies || {}).map(([k, words]) => `<option value="${k}">${words}</option>`).join("")}
    </select>
    <select class="trust" aria-label="Seat ${i + 1} trust" hidden>
      <option value="">weighs the model's answer</option>
      <option value="trust_fit">takes a fitting answer as the answer</option>
    </select>
    <input class="other" placeholder="any OpenRouter slug, like openai/gpt-6-luna" hidden>
    <input class="nick" placeholder="Nickname (optional)" maxlength="20" autocomplete="off" aria-label="Seat ${i + 1} nickname" hidden>`;
  const kindSel = box.querySelector(".kind"), modelSel = box.querySelector(".model"), other = box.querySelector(".other");
  const solverSel = box.querySelector(".solver"), trustSel = box.querySelector(".trust");
  trustSel.value = variant === "trust_fit" ? "trust_fit" : "";
  const strategySel = box.querySelector(".strategy");  // a bot seat may play a strategy: bot:<strategy>
  strategySel.value = kind === "bot" && (setupInfo.bot_strategies || {})[named] ? named : "";
  const nick = box.querySelector(".nick");
  nick.value = name;
  kindSel.value = KIND_NAMES[kind] ? kind : "bot";
  const fill = () => {
    const k = kindSel.value;
    const list = k === "llm" ? setupInfo.models : k === "hybrid" ? setupInfo.hybrid_models : k === "decision" ? setupInfo.decision_models : [];
    modelSel.hidden = list.length === 0 && k !== "llm";
    modelSel.innerHTML = list.map((m) => `<option value="${m}">${m}</option>`).join("") + (k === "llm" ? `<option value="__other">another model…</option>` : "");
    if (list.includes(model)) modelSel.value = model;
    else if (k === "llm" && model) { modelSel.value = "__other"; other.value = model; }
    other.hidden = modelSel.value !== "__other" || modelSel.hidden;
    nick.hidden = k !== "human";
    // A decision seat's solver writes its answers: config's by default, or any model the page lists
    solverSel.hidden = k !== "decision";
    const solvers = setupInfo.models.filter((m) => m !== setupInfo.solver_model);
    solverSel.innerHTML = `<option value="">${setupInfo.solver_model} solves (default)</option>` +
      solvers.map((m) => `<option value="${m}">${m} solves</option>`).join("");
    solverSel.value = solvers.includes(solver) ? solver : "";
    trustSel.hidden = k !== "hybrid";  // the full-trust variant: a fitting answer is the answer until the board rules it out
    strategySel.hidden = k !== "bot";  // a hybrid always plays the standard strategy
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
    if (kind === "human") return kind;
    if (kind === "bot") {
      const strategy = box.querySelector(".strategy").value;
      return strategy ? `bot:${strategy}` : "bot";
    }
    const model = modelSel.value === "__other" ? box.querySelector(".other").value.trim() : modelSel.value;
    const solver = kind === "decision" ? box.querySelector(".solver").value : "";
    const variant = kind === "hybrid" ? box.querySelector(".trust").value : "";
    return model ? `${kind}:${model}${variant ? "+" + variant : ""}${solver ? "@" + solver : ""}` : kind;
  });
}

function chosenNames() {
  return [...document.querySelectorAll(".picker")].map((box) =>
    (box.querySelector(".kind").value === "human" ? box.querySelector(".nick").value.trim() || null : null));
}

async function startGame() {
  const chosen = chosenSeats();
  const names = chosenNames();
  store.set(NAMES_SAVED, names);
  store.set(SAVED, chosen);
  const body = { seats: chosen, names };
  const seedText = $("#seed").value.trim();
  if (seedText) body.seed = Number(seedText);
  $("#start").disabled = true;
  try {
    const r = await fetch("/api/games", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json();
    if (!r.ok) { $("#setup-error").textContent = data.detail || "The game couldn't start."; return; }
    setHash("g=" + data.id);
    connect(data.id, true);
  } finally {
    $("#start").disabled = false;
  }
}

// ---------- A live game ----------

function resetBoard() {
  table = null; prompt = null; thoughts = {}; lastShown = new Set(); over = false; roundList = null;
  thinkingSeat = null; bonusSpun = false; bonusRevealed = false; wheelSignature = "";
  pending.length = 0;
  $("#moves").innerHTML = ""; $("#thinking").innerHTML = ""; $("#banner").hidden = true; $("#answer").hidden = true; $("#call").hidden = true;
  $("#source").hidden = true;
  $("#board").innerHTML = ""; $("#category").textContent = ""; $("#round-line").textContent = "";
  $("#controls").innerHTML = "";
  $("#wheel-rot").innerHTML = ""; $("#wheel-rot").classList.remove("spinning"); wheelAngle = 0;
  $("#wheel-rot").style.transform = "rotate(0deg)";
  $("#wheel-wrap").hidden = true;  // until the new game's first table draws its own wheel
  $("#seats").innerHTML = ""; $("#letters").innerHTML = ""; $("#wedge-line").textContent = "";
  show("game");
}

function connect(id, fresh = false) {
  leave();
  mode = "play";
  gameId = id;
  resetBoard();
  $("#controls").hidden = false; $("#transport").hidden = true;
  replaying = !fresh;  // a game just started here plays from its first event; a reconnect catches up at once
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/api/games/${id}`);
  ws.onmessage = (e) => {
    clearTimeout(replayTimer);
    replayTimer = setTimeout(() => { replaying = false; }, 250);  // a reconnect's history arrives in a burst
    enqueue(JSON.parse(e.data));
  };
  ws.onclose = () => { if (!over && mode === "play") $("#status").textContent += " · disconnected"; };
}

function leave() {
  if (ws) { ws.onclose = null; ws.close(); ws = null; }
  if (rp) rp.playing = false;
}

function send(command) {
  const seat = prompt ? prompt.seat : me;
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ command, seat }));
  prompt = null;
  renderControls();
}

// Events play one at a time. A spin holds the ones after it until the wheel stops, so the next seat's
// highlight, the wedge's result, and the human's controls wait for the wheel.
const pending = [];
let draining = false;
let rush = false;  // a replay step asked for while one plays skips the rest of its animation
const drained = [];

function enqueue(ev) {
  pending.push(ev);
  if (!draining) drain();
}

function settled() {
  return draining || pending.length ? new Promise((done) => drained.push(done)) : Promise.resolve();
}

async function drain() {
  draining = true;
  while (pending.length) {
    const wait = handle(pending.shift());
    if (wait && !replaying && !rush) await pause(wait);
  }
  draining = false;
  rush = false;
  drained.splice(0).forEach((done) => done());
}

function handle(ev) {
  switch (ev.type) {
    case "start":
      seats = ev.seats;
      humans = seats.map((s, i) => (s.kind === "human" ? i : -1)).filter((i) => i >= 0);
      me = humans.length === 1 ? humans[0] : null;  // "You" only when one human plays
      seed = ev.seed;
      $("#thinking-panel").hidden = mode === "play" && humans.length > 0;  // it would give a bot's best guess away
      $("#status").textContent = mode === "replay" ? `Replay · ${rp.meta.name}` : `seed ${seed}`;
      break;
    case "round": {
      const title = ev.round ? `Round ${ev.round}` : "Bonus round";
      $("#round-line").textContent = title;
      if (mode === "play") $("#status").textContent = `${title} · seed ${seed}`;
      startRound(title, ev.category);
      lastShown = new Set();
      addInfo(ev.round ? `${seatName(ev.starts)} ${isYou(ev.starts) ? "start" : "starts"}.` : `${seatName(ev.starts)} ${isYou(ev.starts) ? "play" : "plays"} for an envelope.`);
      if (!replaying) {
        overlay({ who: ev.category || "", text: title.toUpperCase(), tone: "round" });
        pending.unshift({ type: "hide" });
        return ROUND_MS;
      }
      break;
    }
    case "table":
      table = ev;
      $("#banner").hidden = true;
      $("#source").hidden = true;
      $("#board").classList.remove("solved");
      renderTable();
      if (!ev.wheel.length && String(ev.phase).startsWith("bonus") && !bonusSpun) {
        bonusSpun = true;
        if (replaying) { spinBonus(); break; }
        // An empty board, a beat, the envelope wheel, then R S T L N E: the picks wait for all of it
        drawBoard(blankRows(ev.rows), false);
        pending.unshift({ type: "bonus_spin" }, { type: "bonus_free", table: ev });
        return BONUS_EMPTY_MS;
      }
      break;
    case "bonus_spin":
      return spinBonus();
    case "bonus_free":
      overlay({ who: "Every bonus round starts with", text: "R  S  T  L  N  E" });
      pending.unshift({ type: "bonus_lit", table: ev.table });
      return BONUS_FREE_MS;
    case "bonus_lit":
      hideOverlay();
      drawBoard(ev.table.rows, false);  // the free letters light up
      return BONUS_LIT_MS;
    case "thinking":
      thinkingSeat = ev.seat;
      renderControls();
      break;
    case "move": {
      if (!replaying && staged(ev.seat)) {  // a breather after the last move before this one plays
        const gap = GAP_MS - (performance.now() - lastMoveAt);
        if (gap > 40) { pending.unshift(ev); return gap; }
      }
      prompt = null;
      thinkingSeat = null;
      renderControls();
      if (!replaying && LETTER_KINDS.has(ev.kind) && showCall(ev)) {  // every seat's letter, big; then a miss, or the tiles
        pending.unshift({ type: "called", move: ev });
        return CALL_MS;
      }
      if (!replaying && staged(ev.seat)) {
        if (SOLVE_KINDS.has(ev.kind)) {  // a beat on the board, then the answer, then the verdict
          pending.unshift({ type: "solving", move: ev });
          return SOLVE_LEAD_MS;
        }
        const choice = choiceOverlay(ev);
        if (choice) {  // a special wedge choice or the bonus picks, then what came of it
          overlay(choice);
          pending.unshift({ type: "chosen", move: ev });
          return CHOICE_MS;
        }
      }
      if (ev.wedge && !replaying) {  // the wheel turns first; its result shows once it stops
        spinTo(ev.wedge);
        pending.unshift({ type: "landed", move: ev });
        return SPIN_MS;
      }
      if (ev.wedge) spinTo(ev.wedge);
      addMove(ev);
      break;
    }
    case "solving":
      if (showSolve(ev.move)) {
        pending.unshift({ type: "verdict", move: ev.move });
        return SOLVE_MS;
      }
      addMove(ev.move);
      break;
    case "verdict":
      if (["wrong_solve", "bonus_missed", "forfeit"].includes(ev.move.outcome) && !ev.shown) {
        $("#call").classList.add("miss");
        $("#call-who").textContent = "Not it";
        pending.unshift({ ...ev, shown: true });
        return MISS_MS;
      }
      hideOverlay();
      addMove(ev.move);
      break;
    case "called":
      if (["missing", "repeated"].includes(ev.move.outcome) && !ev.shown) {  // the letter isn't there: say so
        showMiss(ev.move);
        pending.unshift({ ...ev, shown: true });
        return MISS_MS;
      }
      hideOverlay();
      addMove(ev.move);
      break;
    case "chosen": {
      const result = !ev.shown && choiceResult(ev.move);
      if (result) {
        overlay(result);
        pending.unshift({ ...ev, shown: true });
        return MISS_MS;
      }
      hideOverlay();
      addMove(ev.move);
      break;
    }
    case "hide":
      hideOverlay();
      lastMoveAt = performance.now() + ROUND_START_MS;  // the new board stands a little longer before its first move
      break;
    case "landed":
      addMove(ev.move);
      $("#wedge-line").innerHTML = `Wedge: <b>${escapeHtml(ev.move.wedge.text)}</b>`;
      return ev.move.seat === me ? 0 : LANDED_MS;
    case "thoughts":
      thoughts[ev.seat] = ev.lines;
      renderThoughts();
      break;
    case "solved":
      drawBoard(ev.rows, true);
      $("#board").classList.add("solved");
      $("#category").textContent = ev.category;
      showSource(ev.source);
      const hold = ev.source ? SOURCE_MS : SOLVED_MS;  // a longer look when the puzzle's origin shows too
      showBanner(ev.bonus && !ev.solved ? `The answer was ${ev.answer}.` : lastMoveText());
      if (ev.bonus) bonusRevealed = true;  // the bonus board's hold stands in for the one before the final scores
      return replaying ? 0 : hold;  // the page holds the solved board itself: it may run behind the server
    case "round_over":
      addInfo(ev.text);
      showSource(ev.source);
      break;
    case "prompt":
      prompt = ev;
      renderControls();
      break;
    case "over":
      if (!replaying && !ev.held && !bonusRevealed) {  // let the result land on the stage before the final scores
        pending.unshift({ ...ev, held: true });
        return OVER_MS;
      }
      over = true;
      hideOverlay();
      renderOver(ev);
      break;
    case "stalled": {
      // A model's calls failed after their retries. The game waits: ask again, or let the seat lose the turn.
      thinkingSeat = null;
      const who = escapeHtml(seatName(ev.seat));
      const box = $("#controls");
      box.innerHTML = `<div class="error"><b>${who}</b>'s model didn't answer: ${escapeHtml(ev.text)}</div>
        <div class="actions"><button class="spin-btn" data-control="retry">Try again</button>
        <button data-control="skip">Skip the turn</button>
        <span class="label">Nothing was played yet, so trying again picks up right here. Skipping counts as ${who}'s forfeit.</span></div>`;
      box.querySelectorAll("[data-control]").forEach((b) => {
        b.onclick = () => {
          if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ control: b.dataset.control }));
          box.innerHTML = `<div class="waiting">${b.dataset.control === "retry" ? `Asking <b>${who}</b>'s model again…` : `Skipping <b>${who}</b>'s turn…`}</div>`;
        };
      });
      return 0;
    }
    case "retrying":
      thinkingSeat = ev.seat;
      renderControls();
      break;
    case "failed":
      over = true;
      if (!table) { setHash(""); showSetup(ev.text); return 0; }
      $("#controls").innerHTML = `<div class="error">${escapeHtml(ev.text)}</div>`;
      break;
  }
  return 0;
}

// ---------- Drawing the table ----------

// A seat's name on the page: a human's nickname, "You" when one human plays unnamed, or its number.
const nameOf = (i) => (seats[i] && seats[i].name) || null;
const isYou = (i) => i === me && !nameOf(i);
const seatName = (i) => nameOf(i) || (isYou(i) ? "You" : `Seat ${i + 1}`);

function renderTable() {
  const t = table;
  if (t.round) $("#round-line").textContent = `Round ${t.round}`;
  drawBoard(t.rows, false);
  $("#category").textContent = t.category;
  drawLetters(new Set(t.used));
  const bonus = !t.wheel.length && String(t.phase).startsWith("bonus");
  if (bonus) drawBonusWheel(); else drawWheel(t.wheel);
  $("#wheel-wrap").hidden = !t.wheel.length && !bonus;
  $("#wedge-line").innerHTML = bonus ? "An envelope, <b>sealed</b> until the end"
    : t.express ? "Riding the <b>Express</b>" : t.wedge ? `Wedge: <b>${escapeHtml(t.wedge.text)}</b>` : "";
  drawSeats();
  drawAnswer();
  renderControls();
}

function drawBoard(rows, solved) {
  const board = $("#board");
  board.innerHTML = "";
  const shown = new Set();
  const animate = !replaying && lastShown.size > 0;
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
        if (animate && !lastShown.has(key)) { tile.classList.add("fresh"); tile.style.animationDelay = `${(c % 14) * 40}ms`; }
      }
      line.appendChild(tile);
    });
    board.appendChild(line);
  });
  lastShown = shown.size ? shown : new Set(["start"]);  // a blank board still counts as drawn
}

function drawLetters(used) {
  $("#letters").innerHTML = [...ALPHABET].map((c) =>
    `<span class="letter${VOWELS.has(c) ? " vowel" : ""}${used.has(c) ? " used" : ""}" aria-label="${c}${used.has(c) ? " used" : ""}">${c}</span>`).join("");
}

function drawSeats() {
  const t = table;
  $("#seats").innerHTML = t.seats.map((label, i) => {
    const kind = seats[i] ? seats[i].kind : "";
    const cards = (t.wild[i] ? `<span class="card">Wild Card</span>` : "") + (t.million[i] ? `<span class="card million">Million</span>` : "");
    const tag = ["llm", "hybrid", "decision"].includes(kind) && i !== me ? ` <span class="kind">(${kind === "llm" ? "model" : kind})</span>` : "";
    return `<div class="seat${t.turn === i && t.phase !== "game_over" ? " turn" : ""}">
      <div class="who">Seat ${i + 1} · <b>${escapeHtml(nameOf(i) || (isYou(i) ? "You" : short(label)))}</b>${tag}</div>
      <div class="bank">${money(t.banks[i])}</div>
      <div class="total">Total ${money(t.totals[i])}</div>
      <div class="cards">${cards}</div>
    </div>`;
  }).join("");
}

function drawAnswer() {
  const box = $("#answer");
  if (mode !== "replay" || !rp || !rp.reveal || !table) { box.hidden = true; return; }
  const round = rp.meta.rounds.find((r) => r.round === table.round) || (table.round === null ? rp.meta.rounds.find((r) => r.round === null) : null);
  box.hidden = !round;
  if (round) box.textContent = `Answer: ${round.answer}`;
}

const expandedThoughts = new Set();  // seats whose thinking the viewer opened in full

function thoughtLine(line) {  // --verbose working arrives indented under its move: keep the nesting
  const depth = line.length - line.trimStart().length;
  return depth ? `<p class="work" style="padding-left:${depth * 0.45}em">${escapeHtml(line.trim())}</p>` : `<p>${escapeHtml(line)}</p>`;
}

function renderThoughts() {
  if (mode === "play" && humans.length) return;  // live, it would give a bot's best guess away; a replay shows it all
  const box = $("#thinking");
  box.innerHTML = Object.keys(thoughts).sort().map((s) =>
    `<div class="think s${s}"><b>Seat ${Number(s) + 1} · ${escapeHtml(short(seats[s] ? seats[s].label : ""))}</b>
      <div class="think-body${expandedThoughts.has(s) ? " open" : ""}">${thoughts[s].map(thoughtLine).join("")}</div>
      <button class="more" data-seat="${s}" hidden>${expandedThoughts.has(s) ? "Show less" : "Show all"}</button></div>`).join("");
  box.querySelectorAll(".think").forEach((t) => {  // a button only where six lines don't hold it all
    const body = t.querySelector(".think-body"), more = t.querySelector(".more");
    more.hidden = !(body.classList.contains("open") || body.scrollHeight > body.clientHeight + 2);
    more.onclick = () => {
      const s = more.dataset.seat;
      if (expandedThoughts.has(s)) expandedThoughts.delete(s); else expandedThoughts.add(s);
      renderThoughts();
    };
  });
}

// The Moves panel: a section per round, newest first, each move marked by its seat and what it did.

function startRound(title, category) {
  const sec = document.createElement("section");
  sec.className = "mround";
  sec.innerHTML = `<h3>${escapeHtml(title)}<span>${escapeHtml(category || "")}</span></h3><ol></ol>`;
  $("#moves").prepend(sec);
  roundList = sec.querySelector("ol");
}

function moveClass(ev) {
  const o = ev.outcome, k = ev.kind, events = ev.events || [];
  if (o === "solved" || o === "bonus_solved") return "solve";
  if (o === "bankrupt" || o === "flipped_bankrupt" || o === "lose_a_turn" || events.includes("bankrupt")) return "bust";
  if (o === "wrong_solve" || o === "bonus_missed" || o === "forfeit") return "wrong";
  if (["keep", "flip", "pass", "play", "use_wild"].includes(k) || o === "flipped_prize" || o === "rode_express") return "special";
  return "";
}

function addMove(ev) {
  if (!roundList) startRound("Start", "");
  const li = document.createElement("li");
  li.className = `mv s${ev.seat} ${moveClass(ev)}`;
  li.innerHTML = `<span class="dot"></span><span>${escapeHtml(ev.text)}${ev.note ? `<span class="note">${escapeHtml(ev.note)}</span>` : ""}</span>`;
  if (mode === "replay") { li.dataset.index = ev.index; li.onclick = () => seek(ev.index); }
  roundList.prepend(li);
  lastMoveAt = performance.now();
}

function addInfo(text) {
  if (!roundList) startRound("Start", "");
  const li = document.createElement("li");
  li.className = "mv info";
  li.innerHTML = `<span></span><span>${escapeHtml(text)}</span>`;
  roundList.prepend(li);
}

function lastMoveText() {
  const first = $("#moves .mv:not(.info)");
  return first ? first.querySelector("span:last-child").firstChild.textContent : "";
}

// The overlay over the board: who is doing what, a big letter or a line of text, and a tone (a miss, a good
// result, or a round's card).
function overlay({ who = "", big = null, text = null, tone = "" }) {
  const box = $("#call"), letter = $("#call-letter"), answer = $("#call-answer");
  $("#call-who").textContent = who;
  letter.hidden = big === null;
  if (big !== null) { letter.textContent = big; letter.classList.toggle("vowel", VOWELS.has(big)); }
  answer.hidden = text === null;
  if (text !== null) answer.textContent = text;
  box.className = `call ${tone}`.trim();
  box.hidden = false;
  $("#banner").hidden = true;  // the banner sits on the board's edge, under the overlay's reach
  void box.offsetWidth;
  box.classList.add("pop");  // restart the pop each time
}

function hideOverlay() {
  $("#call").hidden = true;
}

const doing = (seat, verb) => `${seatName(seat)} ${isYou(seat) ? verb.replace(/s$/, "") : verb}`;

function showCall(ev) {
  const letter = (ev.text.match(/(?:called|bought) ([A-Z])/) || [])[1];
  if (!letter) return false;
  overlay({ who: doing(ev.seat, ev.kind === "buy_vowel" ? "buys" : "calls"), big: letter });
  return true;
}

function showMiss(ev) {
  const letter = (ev.text.match(/(?:called|bought) ([A-Z])/) || [])[1] || "";
  overlay({ who: ev.outcome === "repeated" ? `${letter} was already called` : `No ${letter}`, big: letter, tone: "miss" });
}

function showSolve(ev) {
  const m = ev.text.match(/solved it: (.+?)! Banked|tried "(.+?)"\.|solved the bonus puzzle: (.+?)! The envelope|guessed "(.+?)"\./);
  const answer = m && (m[1] || m[2] || m[3] || m[4]);
  if (!answer) return false;
  overlay({ who: doing(ev.seat, "solves"), text: answer });
  return true;
}

function choiceOverlay(ev) {
  const on = (wedge) => `${seatName(ev.seat)} · ${wedge}`;  // the caption: who, and which wedge; the big text: what they did
  switch (ev.kind) {
    case "keep": {
      const amount = (ev.text.match(/kept the (\$[\d,]+)/) || [])[1];
      return { who: on("Mystery wedge"), text: amount ? `Kept ${amount}` : "Kept" };
    }
    case "flip": return { who: on("Mystery wedge"), text: "Flips!" };
    case "play": return { who: on("Express"), text: "Rides!" };
    case "pass": return { who: on("Express"), text: "Passes" };
    case "use_wild": return { who: on("Wild Card"), text: ev.outcome === "used_wild" ? "Spent!" : "Kept" };
    case "bonus_picks": {
      const m = ev.text.match(/picked (.+?) and ([A-Z])\./);
      return m ? { who: doing(ev.seat, "picks"), text: `${m[1]}  ${m[2]}` } : null;
    }
  }
  return null;
}

function choiceResult(ev) {
  if (ev.outcome === "flipped_prize") return { who: "Behind the wedge", text: "$10,000!", tone: "good" };
  if (ev.outcome === "flipped_bankrupt") return { who: "Behind the wedge", text: "BANKRUPT", tone: "miss" };
  return null;
}

// Where the puzzle came from, once its round is over: an aired puzzle's season, episode, air date and round;
// a generated one's deck.
function showSource(source) {
  const box = $("#source");
  box.hidden = !source;
  if (!source) return;
  if (source.kind === "generated") {
    box.textContent = `Written for rstlne · ${(source.decks || []).join(", ")}`;
    return;
  }
  const first = (source.airings || [])[0] || {};
  const when = first.date ? new Date(`${first.date}T12:00:00`).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" }) : "";
  const round = first.round === "BR" ? "bonus round" : first.round ? `round ${String(first.round).replace(/[^0-9]/g, "")}` : "";
  const episode = first.season_episode ? `episode ${first.season_episode} (#${first.episode} overall)` : first.episode ? `episode #${first.episode}` : "";
  const parts = [first.season ? `Aired in season ${first.season}` : "Aired", episode, when, round].filter(Boolean);
  const more = (source.airings || []).length > 1 ? ` · aired ${source.airings.length} times` : "";
  box.textContent = parts.join(" · ").replace(" · episode", ", episode") + more;
}

function showBanner(text) {
  const b = $("#banner");
  b.textContent = text;
  b.hidden = !text;
}

// ---------- The wheel ----------

const CASH = ["--w1", "--w2", "--w3", "--w4", "--w5", "--w6", "--w7", "--w8"];
const LIGHT = new Set(["--w2", "--w8"]);

function wedgeStyle(w) {
  switch (w.kind) {
    case "bankrupt": return ["var(--w-bankrupt)", "#fff"];
    case "lose_a_turn": return ["var(--w-lose)", "#1b1030"];
    case "free_play": return ["var(--w-free)", "#1b1030"];
    case "mystery": return ["var(--w-mystery)", "#fff"];
    case "express": return ["var(--w-express)", "#fff"];
    case "million": return ["var(--w-million)", "#1b1030"];
  }
  const tone = CASH[(w.number - 1) % CASH.length];
  return [`var(${tone})`, LIGHT.has(tone) ? "#1b1030" : "#fff"];
}

function wedgeLabel(w) {
  return { bankrupt: "BANKRUPT", lose_a_turn: "LOSE A TURN", free_play: "FREE PLAY", mystery: "MYSTERY", express: "EXPRESS", million: "MILLION" }[w.kind] || `${w.value}`;
}

const point = (r, deg) => [r * Math.sin(deg * Math.PI / 180), -r * Math.cos(deg * Math.PI / 180)];

function drawWheel(thirds) {
  if (!thirds.length) return;
  const signature = JSON.stringify(thirds.map((w) => [w.kind, w.value, w.wild]));
  if (signature === wheelSignature) return;
  wheelSignature = signature;
  let svg = "";
  thirds.forEach((w, i) => {
    const a1 = i * 5, a2 = a1 + 5;
    const [x1, y1] = point(103, a1), [x2, y2] = point(103, a2);
    svg += `<path d="M0 0 L${x1.toFixed(2)} ${y1.toFixed(2)} A103 103 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z" fill="${wedgeStyle(w)[0]}"/>`;
  });
  for (let k = 0; k < thirds.length / 3; k++) {
    const [x, y] = point(103, k * 15);
    svg += `<line x1="0" y1="0" x2="${x.toFixed(2)}" y2="${y.toFixed(2)}" stroke="rgba(0,0,0,.35)" stroke-width=".7"/>`;
    const [px, py] = point(106.5, k * 15);
    svg += `<circle cx="${px.toFixed(2)}" cy="${py.toFixed(2)}" r="2.1" fill="#fff3c4" stroke="#8a5a00" stroke-width=".6"/>`;
    const mid = thirds[k * 3 + 1];
    const text = wedgeLabel(mid);
    const size = text.length > 6 ? 5.6 : 8.4;
    svg += `<text transform="rotate(${k * 15 + 7.5}) translate(0 -96) rotate(90)" font-size="${size}" text-anchor="start" dominant-baseline="middle" fill="${wedgeStyle(mid)[1]}">${text}${mid.wild ? " ★" : ""}</text>`;
  }
  const g = $("#wheel-rot");
  g.innerHTML = svg;
  g.style.transform = `rotate(${wheelAngle}deg)`;
}

// The bonus wheel: 24 sealed envelopes. The engine picks the envelope from the seed and keeps it hidden, so the
// drawing lands on one of 24 identical envelopes for show; where it lands says nothing about what's inside.
function drawBonusWheel() {
  if (wheelSignature === "bonus") return;
  wheelSignature = "bonus";
  let svg = "";
  for (let k = 0; k < 24; k++) {
    const a1 = k * 15, a2 = a1 + 15;
    const [x1, y1] = point(103, a1), [x2, y2] = point(103, a2);
    svg += `<path d="M0 0 L${x1.toFixed(2)} ${y1.toFixed(2)} A103 103 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z" fill="${k % 2 ? "#2a1a5c" : "#3a2478"}" stroke="rgba(255,201,74,.35)" stroke-width=".6"/>`;
    const [px, py] = point(106.5, a1);
    svg += `<circle cx="${px.toFixed(2)}" cy="${py.toFixed(2)}" r="2.1" fill="#fff3c4" stroke="#8a5a00" stroke-width=".6"/>`;
    svg += `<g transform="rotate(${a1 + 7.5}) translate(0 -80)"><rect x="-7" y="-5" width="14" height="10" rx="1.2" fill="#fff3d6" stroke="#b77a12" stroke-width=".6"/>`
      + `<path d="M-7 -5 L0 1 L7 -5" fill="none" stroke="#b77a12" stroke-width=".6"/></g>`;
  }
  const g = $("#wheel-rot");
  g.innerHTML = svg;
  g.style.transform = `rotate(${wheelAngle}deg)`;
}

// The board with every letter hidden: the bonus puzzle before R S T L N E go up. Punctuation shows, as on the board.
function blankRows(rows) {
  return rows.map((row) => row.map((ch) => (ch === " " || !/[A-Z]/.test(ch) ? ch : "_")));
}

function spinBonus() {
  const k = Math.floor(Math.random() * 24);
  const target = ((-(k * 15 + 7.5) - wheelAngle) % 360 + 360) % 360;
  wheelAngle += (replaying ? 0 : 1080) + target;
  const g = $("#wheel-rot");
  g.classList.toggle("spinning", !replaying);
  g.style.transform = `rotate(${wheelAngle}deg)`;
  return replaying ? 0 : SPIN_MS;
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
  $("#wedge-line").innerHTML = replaying ? `Wedge: <b>${escapeHtml(wedge.text)}</b>` : "Spinning…";
}

// ---------- The human's controls ----------

function renderControls() {
  const box = $("#controls");
  clearInterval(clockTimer);
  if (mode !== "play") return;
  if (over) { box.innerHTML = ""; return; }
  if (!prompt || !humans.includes(prompt.seat)) {
    const turn = table ? table.turn : null;
    const who = turn === null ? "" : `<b>${escapeHtml(seatName(turn))}</b> (${escapeHtml(short(table.seats[turn]))})`;
    box.innerHTML = turn === null ? "" : `<div class="waiting">${isYou(turn) ? "Your move…"
      : humans.includes(turn) ? `<b>${escapeHtml(seatName(turn))}</b> is up.`
      : thinkingSeat === turn ? `${who} is thinking<span class="dots"></span>` : `${who} is on the wheel.`}</div>`;
    return;
  }
  const p = prompt;
  const used = new Set(table ? table.used : []);
  const legal = new Set(p.legal);
  let html = humans.length > 1 || nameOf(p.seat) ? `<div class="whose seat-c${p.seat}"><b>${escapeHtml(seatName(p.seat))}</b>, you're up.</div>` : "";
  if (p.error) html += `<div class="error">${escapeHtml(p.error)}</div>`;
  const keys = (letters, cmd) => `<div class="keys">${[...letters].map((c) =>
    `<button class="key${VOWELS.has(c) ? " vowel" : ""}" data-cmd="${cmd(c)}" ${used.has(c) ? "disabled" : ""} aria-label="${c}">${c}</button>`).join("")}</div>`;

  switch (p.phase) {
    case "turn":
    case "express":
      html += `<div class="actions">
        ${legal.has("spin") ? `<button class="spin-btn" data-cmd="s">Spin</button>` : ""}
        ${p.phase === "express" ? `<span class="label">Riding the Express: call a consonant, buy a vowel, or solve.</span>` : `<span class="label">Spin, buy a vowel, or solve. Press S to spin.</span>`}
      </div>`;
      if (p.phase === "express" && legal.has("call_consonant")) html += keys(CONSONANTS, (c) => c);
      if (legal.has("buy_vowel")) html += `<div class="actions"><span class="label">Buy a vowel ($250):</span>${keys("AEIOU", (c) => `v ${c}`)}</div>`;
      if (legal.has("solve")) html += solveBox("Solve", (text) => `solve ${text}`);
      break;
    case "call_consonant":
    case "wild_consonant":
      html += `<div class="label">${p.phase === "wild_consonant" ? "Call your extra consonant." : "Call a consonant, or type it."}</div>` + keys(CONSONANTS, (c) => c);
      break;
    case "free_play":
      html += `<div class="label">Free Play: call any letter. A vowel is free, and a miss keeps your turn.</div>` + keys(ALPHABET, (c) => c);
      break;
    case "mystery_choice":
      html += `<div class="actions"><span class="label">Keep the money, or flip the wedge: $10,000 or Bankrupt.</span>
        <button data-cmd="keep">Keep</button><button class="go" data-cmd="flip">Flip it</button></div>`;
      break;
    case "express_choice":
      html += `<div class="actions"><span class="label">Ride the Express? Any miss or wrong solve is Bankrupt.</span>
        <button data-cmd="pass">Pass</button><button class="go" data-cmd="play">Ride</button></div>`;
      break;
    case "wild_choice":
      html += `<div class="actions"><span class="label">Spend the Wild Card on one more consonant at this value?</span>
        <button data-cmd="no">Keep the card</button><button class="go" data-cmd="wild">Spend it</button></div>`;
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
    <button class="go" type="submit">${label}</button></form>`;
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
    <div class="actions"><button class="spin-btn" data-picks-go disabled>Reveal</button><span class="label" data-picks-left></span></div>`;
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

// ---------- Replays ----------

const STOPS = [
  ["solve", "Solves"], ["wrong", "Wrong solves"], ["bust", "Bankrupt & Lose a Turn"], ["round", "New rounds"],
  ["special", "Mystery, Express, Wild"], ["bonus", "Bonus round"], ["s0", "Seat 1"], ["s1", "Seat 2"], ["s2", "Seat 3"],
];

async function showReplays() {
  leave();
  mode = "replay";
  show("replays");
  $("#status").textContent = "";
  const list = $("#replay-list");
  list.innerHTML = `<div class="empty">Reading the log folder…</div>`;
  const r = await fetch("/api/logs");
  if (!r.ok) { list.innerHTML = `<div class="empty">Replays are off on this server.</div>`; return; }
  const data = await r.json();
  if (!data.logs.length) { list.innerHTML = `<div class="empty">No games in ${escapeHtml(data.folder)} yet.</div>`; return; }
  list.innerHTML = data.logs.map((l) => {
    const when = l.started ? new Date(l.started).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : l.name;
    const best = l.totals ? Math.max(...l.totals) : null;
    const res = l.finished ? l.totals.map((t, i) => (t === best ? `<b>${money(t)}</b>` : money(t))).join(" · ") : "unfinished";
    return `<button class="replay-row" data-name="${escapeHtml(l.name)}">
      <span class="when">${escapeHtml(when)}</span>
      <span class="who">${l.seats.map((s, i) => `<span class="pill s${i}" title="${escapeHtml(s)}">${escapeHtml(short(s))}</span>`).join("")}</span>
      <span class="seedcol">seed ${l.seed}</span>
      <span class="res">${res}</span></button>`;
  }).join("");
  list.querySelectorAll("[data-name]").forEach((b) => { b.onclick = () => { setHash("r=" + encodeURIComponent(b.dataset.name)); openReplay(b.dataset.name); }; });
}

async function openReplay(name) {
  leave();
  mode = "replay";
  const r = await fetch(`/api/logs/${encodeURIComponent(name)}`);
  const data = await r.json();
  if (!r.ok) { await showReplays(); $("#replay-list").insertAdjacentHTML("afterbegin", `<div class="setup-error">${escapeHtml(data.detail || "That log couldn't be replayed.")}</div>`); return; }
  const groups = [[]];
  for (const ev of data.events) {
    if (ev.type === "move") groups.push([ev]);
    else groups[groups.length - 1].push(ev);
  }
  rp = { meta: data.meta, groups, pos: 0, playing: false, speed: 1, reveal: false, stops: new Set(store.get(STOPS_SAVED, ["solve", "bust", "round"])) };
  $("#controls").hidden = true; $("#transport").hidden = false;
  seek(0);
}

function seek(k) {
  if (!rp) return;
  rp.playing = false;
  k = Math.max(0, Math.min(k, rp.groups.length - 1));
  resetBoard();
  $("#controls").hidden = true; $("#transport").hidden = false;
  replaying = true;
  for (let i = 0; i <= k; i++) for (const ev of rp.groups[i]) handle(ev);
  replaying = false;
  rp.pos = k;
  renderTransport();
}

async function stepForward() {
  if (!rp || rp.pos >= rp.groups.length - 1) return false;
  if (draining) rush = true;
  rp.pos += 1;
  updatePosition();
  if ($("#over").hidden === false) show("game");
  for (const ev of rp.groups[rp.pos]) enqueue(ev);
  await settled();
  renderTransport();
  return true;
}

function stopsAt(group) {
  const move = group[0];
  if (!move || move.type !== "move") return false;
  const cls = moveClass(move);
  if (cls && rp.stops.has(cls)) return true;
  if (rp.stops.has("round") && group.some((e) => e.type === "round")) return true;
  if (rp.stops.has("bonus") && (move.kind === "bonus_picks" || move.kind === "bonus_solve")) return true;
  return rp.stops.has(`s${move.seat}`);
}

async function play() {
  if (!rp) return;
  rp.playing = !rp.playing;
  renderTransport();
  while (rp && rp.playing) {
    const moved = await stepForward();
    if (!moved || !rp.playing) break;
    if (stopsAt(rp.groups[rp.pos])) break;
    await pause(900 / rp.speed);
  }
  if (rp) { rp.playing = false; renderTransport(); }
}

function updatePosition() {
  const pos = $("#transport .pos"), scrub = $('#transport [data-t="scrub"]');
  if (pos) pos.textContent = `Move ${rp.pos} of ${rp.groups.length - 1}`;
  if (scrub) scrub.value = rp.pos;
}

function renderTransport() {
  if (!rp) return;
  const last = rp.groups.length - 1;
  const box = $("#transport");
  box.innerHTML = `
    <div class="bar">
      <button class="icon" data-t="start" title="Start (Home)" aria-label="Back to the start">⏮</button>
      <button class="icon" data-t="back" title="Back a move (←)" aria-label="Back a move">◀</button>
      <button class="spin-btn" data-t="play" title="Play or pause (space)">${rp.playing ? "Pause" : "Play"}</button>
      <button class="icon" data-t="fwd" title="Forward a move (→)" aria-label="Forward a move">▶</button>
      <button class="icon" data-t="end" title="End (End)" aria-label="To the end">⏭</button>
      <select data-t="speed" aria-label="Speed">${[0.5, 1, 2, 4].map((s) => `<option value="${s}" ${s === rp.speed ? "selected" : ""}>${s}×</option>`).join("")}</select>
      <span class="pos">Move ${rp.pos} of ${last}</span>
      <label class="toggle"><input type="checkbox" data-t="reveal" ${rp.reveal ? "checked" : ""}> Show the answer</label>
    </div>
    <input type="range" min="0" max="${last}" value="${rp.pos}" data-t="scrub" aria-label="Move">
    <div class="stops"><span class="label">Stop at:</span>${STOPS.map(([key, name]) =>
      `<button class="chip${rp.stops.has(key) ? " on" : ""}" data-stop="${key}">${name}</button>`).join("")}</div>`;
  box.querySelector('[data-t="start"]').onclick = () => seek(0);
  box.querySelector('[data-t="back"]').onclick = () => seek(rp.pos - 1);
  box.querySelector('[data-t="fwd"]').onclick = () => { rp.playing = false; stepForward(); };
  box.querySelector('[data-t="end"]').onclick = () => seek(last);
  box.querySelector('[data-t="play"]').onclick = play;
  box.querySelector('[data-t="speed"]').onchange = (e) => { rp.speed = Number(e.target.value); };
  box.querySelector('[data-t="reveal"]').onchange = (e) => { rp.reveal = e.target.checked; drawAnswer(); };
  box.querySelector('[data-t="scrub"]').oninput = (e) => seek(Number(e.target.value));
  box.querySelectorAll("[data-stop]").forEach((b) => {
    b.onclick = () => {
      const key = b.dataset.stop;
      if (rp.stops.has(key)) rp.stops.delete(key); else rp.stops.add(key);
      store.set(STOPS_SAVED, [...rp.stops]);
      b.classList.toggle("on", rp.stops.has(key));
    };
  });
  document.querySelectorAll(".mv.now").forEach((m) => m.classList.remove("now"));
  const now = document.querySelector(`.mv[data-index="${rp.pos}"]`);
  if (now) now.classList.add("now");
}

// ---------- Keys ----------

document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, select, textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
  if (mode === "replay" && rp && !$("#game").hidden) {
    const acts = { ArrowRight: () => { rp.playing = false; stepForward(); }, ArrowLeft: () => seek(rp.pos - 1), " ": play, Home: () => seek(0), End: () => seek(rp.groups.length - 1) };
    if (acts[e.key]) { e.preventDefault(); acts[e.key](); }
    return;
  }
  if (!prompt || !humans.includes(prompt.seat)) return;
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
  show("over");
  const box = $("#over");
  const totals = ev.totals, best = Math.max(...totals);
  const b = ev.bonus;
  const rows = b ? b.rows.map((row) => `<div class="row">${row.map((ch) => (ch === " " ? `<div class="tile gap"></div>` : `<div class="tile shown">${ch}</div>`)).join("")}</div>`).join("") : "";
  const replayButtons = mode === "replay" ? `<button data-o="back">Back to the game</button><button data-o="list">All replays</button>` : "";
  box.innerHTML = `
    <h1>${winnerLine(totals)}</h1>
    ${b ? `<div class="board-wrap"><div class="round-line">Bonus round · ${escapeHtml(b.category)}</div><div class="board">${rows}</div>
      <div class="category">${escapeHtml(seatName(b.seat))} ${b.solved ? "solved it" : "missed it"}. The envelope held ${b.envelope_text}.</div></div>` : ""}
    <table class="totals"><thead><tr><th>Seat</th><th class="num">Before the bonus</th><th class="num">Final total</th></tr></thead>
      <tbody>${totals.map((t, i) => `<tr class="${t === best ? "winner" : ""}"><td>Seat ${i + 1} · ${escapeHtml(nameOf(i) || (isYou(i) ? "You" : short(seats[i] ? seats[i].label : "")))}</td>
        <td class="num">${money(ev.before_bonus[i])}</td><td class="num">${money(t)}</td></tr>`).join("")}</tbody></table>
    ${ev.usage.length ? `<div class="usage">${ev.usage.map((u) => `${escapeHtml(u.model)}: ${u.calls} calls, ${Number(u.tokens).toLocaleString()} tokens (${Number(u.cached).toLocaleString()} from cache), $${Number(u.cost).toFixed(4)}`).join("<br>")}</div>` : ""}
    <div class="usage">Log: <code>${escapeHtml(ev.log)}</code></div>
    <div class="actions"><button class="spin-btn" data-o="new">New game</button>${replayButtons}</div>`;
  box.querySelector('[data-o="new"]').onclick = newGame;
  if (mode === "replay") {
    box.querySelector('[data-o="back"]').onclick = () => seek(rp.groups.length - 1 - 1 >= 0 ? rp.groups.length - 2 : 0);
    box.querySelector('[data-o="list"]').onclick = () => { setHash("replays"); showReplays(); };
  } else {
    $("#status").textContent = "Game over";
  }
}

function winnerLine(totals) {
  const best = Math.max(...totals);
  const winners = totals.map((t, i) => (t === best ? i : -1)).filter((i) => i >= 0);
  if (winners.length > 1) return `A tie at ${money(best)}`;
  return isYou(winners[0]) ? `You won with ${money(best)}!` : `${escapeHtml(seatName(winners[0]))} wins with ${money(best)}!`;
}

function newGame() {
  if (gameId && mode === "play") fetch(`/api/games/${gameId}`, { method: "DELETE" }).catch(() => {});
  gameId = null; rp = null; mode = "play";
  history.replaceState(null, "", location.pathname);
  routed = "";
  showSetup();
}

// ---------- Start ----------

$("#start").onclick = startGame;
$("#brand").onclick = (e) => { e.preventDefault(); newGame(); };
$("#nav-play").onclick = newGame;
$("#nav-replays").onclick = () => { setHash("replays"); showReplays(); };
document.querySelectorAll("[data-preset]").forEach((b) => { b.onclick = () => drawPickers(b.dataset.preset.split(",")); });

// The address after # says what's on screen: g=<game>, r=<log>, or replays. Changes the page makes itself are
// remembered, so only the back and forward buttons, or a typed address, route again.
let routed = null;
function setHash(h) {
  routed = h;
  if (location.hash.slice(1) !== h) location.hash = h;
}

function route() {
  const h = location.hash.slice(1);
  if (h === routed) return;
  routed = h;
  if (h.startsWith("g=")) connect(h.slice(2));
  else if (h.startsWith("r=")) openReplay(decodeURIComponent(h.slice(2)));
  else if (h === "replays") showReplays();
  else showSetup();
}
window.addEventListener("hashchange", route);
route();

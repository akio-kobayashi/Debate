const API_BASE = window.DEBATE_API_BASE || "";
const TURN_LABELS = {
  define: "定義",
  opening: "立論",
  organize: "整理",
  rebuttal: "反論",
  closing: "最終弁論",
  summary: "まとめ",
};
const TURN_PLAN = [
  ["C", "define"], ["A", "opening"], ["B", "opening"],
  ["C", "organize"], ["A", "rebuttal"], ["B", "rebuttal"],
  ["A", "closing"], ["B", "closing"], ["C", "summary"],
];

const state = {
  debateId: null,
  session: null,
  events: null,
  activeTurn: null,
  liveText: { A: "", B: "", C: "" },
  eventsReady: false,
};

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value || "").replace(/[&<>'"]/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
}[char]));

async function requestJson(path, options = {}) {
  const response = await fetch(API_BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "サーバーとの通信に失敗しました");
  }
  return payload;
}

function setFooter(status, message, loading = false) {
  $("#footerStatus").textContent = status;
  $("#footerMessage").textContent = message;
  $("#footerSpinner").style.visibility = loading ? "visible" : "hidden";
}

function roundNumber() {
  if (!state.session) return 1;
  if (state.activeTurn !== null) return state.activeTurn + 1;
  return Math.min((state.session.next_turn || 0) + 1, state.session.total_turns || 9);
}

function renderRound() {
  const round = roundNumber();
  $("#progressTitle").textContent = "Round " + round;
  $("#progressCount").textContent = "/ 9";
  $("#roundProgressBar").style.width = ((round / 9) * 100) + "%";
}

function latestMessage(speaker) {
  const messages = state.session?.messages || [];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].speaker === speaker) return messages[index];
  }
  return null;
}

function roleStatus(speaker) {
  if (state.session?.status === "generating" && state.session.current_speaker === speaker) {
    return '<span class="status-dot"></span>生成中';
  }
  if (state.session?.status === "stopping" && state.session.current_speaker === speaker) {
    return '<span class="status-dot idle-dot"></span>停止中';
  }
  return latestMessage(speaker)
    ? '<span class="status-dot"></span>完了'
    : '<span class="status-dot idle-dot"></span>待機中';
}

function renderRolePanels() {
  const aText = state.liveText.A || latestMessage("A")?.text || "";
  const bText = state.liveText.B || latestMessage("B")?.text || "";
  $("#bodyA").innerHTML = aText
    ? "<p>" + escapeHtml(aText) + "</p>"
    : '<p class="empty-state">テーマを入力すると、ここに表示されます。</p>';
  $("#bodyB").innerHTML = bText
    ? "<p>" + escapeHtml(bText) + "</p>"
    : '<p class="empty-state">テーマを入力すると、ここに表示されます。</p>';
  $("#statusA").innerHTML = roleStatus("A");
  $("#statusB").innerHTML = roleStatus("B");
  $("#statusC").innerHTML = roleStatus("C");

  if (!state.session) {
    $("#bodyC").innerHTML = '<p class="empty-state">テーマを入力すると、整理結果が表示されます。</p>';
    return;
  }
  const context = state.session.theme_context || {};
  const current = context.current_issue || context.evaluation_axes || "テーマから論点を抽出しています。";
  const activeSpeaker = state.session.current_speaker;
  const activeKind = state.session.current_kind;
  const next = activeSpeaker && activeKind
    ? activeSpeaker + "に" + TURN_LABELS[activeKind] + "をお願いします。"
    : state.session.status === "finished"
      ? "ディベートが終了しました。"
      : (context.next_instruction || nextInstruction());
  $("#bodyC").innerHTML = '<div class="c-section"><h3>現在の論点</h3><div class="c-box">' +
    escapeHtml(current) + '</div></div><div class="c-section"><h3>次の指示</h3><div class="c-box">' +
    escapeHtml(next) + "</div></div>";
}

function nextInstruction() {
  const next = TURN_PLAN[state.session?.next_turn || 0];
  if (!next) return "最終整理を確認してください。";
  return next[0] + "に" + TURN_LABELS[next[1]] + "をお願いします。";
}

function renderTimeline() {
  const messages = (state.session?.messages || []).slice(-4);
  if (!messages.length) {
    $("#historyList").innerHTML = '<p class="empty-state">テーマを入力すると、進行履歴が表示されます。</p>';
    return;
  }
  $("#historyList").innerHTML = messages.map((message, index) => {
    const speaker = message.speaker;
    const avatarClass = speaker === "A" ? "a" : speaker === "B" ? "b" : "c";
    const arrow = index < messages.length - 1 ? '<span class="timeline-arrow">→</span>' : "";
    const label = TURN_LABELS[message.kind] || message.kind;
    return '<div class="timeline-item ' + (index === messages.length - 1 ? "active" : "") + '">' +
      '<div class="timeline-avatar ' + avatarClass + '">' + speaker + '</div>' +
      '<div class="timeline-copy"><strong>' + escapeHtml(label) + '</strong><small>' +
      escapeHtml(message.speaker + "の発言") + "</small></div></div>" + arrow;
  }).join("");
}

function renderControls() {
  renderRound();
  const generating = ["generating", "stopping"].includes(state.session?.status);
  const finished = state.session?.status === "finished";
  $("#startButton").disabled = generating || finished;
  $("#stopButton").disabled = !generating;
  $("#startButton").innerHTML = finished ? "終了" : "次の発言 <span>›</span>";
  if (!state.session) {
    setFooter("待機中", "テーマを入力して開始してください");
  } else if (state.session.status === "generating") {
    setFooter((state.session.current_speaker || "LLM") + "が生成中", "しばらくお待ちください…", true);
  } else if (state.session.status === "stopping") {
    setFooter("停止中", "生成を停止しています…");
  } else if (state.session.status === "error") {
    setFooter("エラー", state.session.error_message || "サーバーエラーが発生しました");
  } else if (finished) {
    setFooter("完了", "ディベートの最終整理が完了しました");
  } else {
    setFooter("待機中", "次の発言を押して進行します");
  }
}

function render() {
  renderControls();
  renderRolePanels();
  renderTimeline();
}

function applySession(session) {
  state.session = session;
  state.debateId = session.debate_id;
  if (session.model) $("#modelName").textContent = session.model;
  if (session.status !== "generating") state.activeTurn = null;
  render();
}

function handleEvent(event) {
  let payload;
  try {
    payload = JSON.parse(event.data);
  } catch {
    return;
  }
  if (event.type === "state") {
    applySession(payload);
    return;
  }
  if (event.type === "turn_started") {
    state.activeTurn = payload.turn_index;
    state.liveText[payload.speaker] = "";
    if (payload.state) state.session = payload.state;
    render();
    return;
  }
  if (event.type === "token") {
    state.liveText[payload.speaker] = (state.liveText[payload.speaker] || "") + (payload.text || "");
    if (state.session) {
      state.session.status = "generating";
      state.session.current_speaker = payload.speaker;
    }
    render();
    return;
  }
  if (event.type === "turn_completed") {
    state.liveText[payload.speaker] = "";
    if (payload.state) applySession(payload.state);
    return;
  }
  if (["turn_stopped", "stopping", "debate_finished"].includes(event.type)) {
    if (payload.state) applySession(payload.state);
    return;
  }
  if (event.type === "error") {
    if (payload.state) applySession(payload.state);
    else setFooter("エラー", payload.message || "サーバーエラーが発生しました");
  }
}

async function connectEvents() {
  if (!state.debateId) return;
  if (state.events) state.events.close();
  state.eventsReady = false;
  const url = API_BASE + "/api/debates/" + encodeURIComponent(state.debateId) + "/events";
  state.events = new EventSource(url);
  ["state", "turn_started", "token", "turn_completed", "turn_stopped", "stopping", "debate_finished", "error"]
    .forEach((eventName) => state.events.addEventListener(eventName, handleEvent));
  state.events.onerror = () => {
    state.eventsReady = false;
    if (state.session?.status !== "finished") setFooter("再接続中", "SSE接続を再試行しています…");
  };
  await new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error("SSE接続がタイムアウトしました")), 8000);
    state.events.addEventListener("open", () => {
      window.clearTimeout(timeout);
      state.eventsReady = true;
      resolve();
    }, { once: true });
  });
}

async function startOrNext(event) {
  event.preventDefault();
  if (state.session?.status === "generating") return;
  try {
    if (!state.debateId) {
      const theme = $("#themeInput").value.trim();
      if (!theme) {
        setFooter("入力待ち", "テーマを入力してください");
        $("#themeInput").focus();
        return;
      }
      applySession(await requestJson("/api/debates", {
        method: "POST",
        body: JSON.stringify({ theme }),
      }));
      await connectEvents();
    } else if (!state.eventsReady) {
      await connectEvents();
    }
    await requestJson("/api/debates/" + encodeURIComponent(state.debateId) + "/next", { method: "POST" });
  } catch (error) {
    setFooter("接続エラー", error.message || "サーバーに接続できません");
  }
}

async function stopGeneration() {
  if (!state.debateId) return;
  try {
    await requestJson("/api/debates/" + encodeURIComponent(state.debateId) + "/stop", { method: "POST" });
  } catch (error) {
    setFooter("停止エラー", error.message || "停止要求に失敗しました");
  }
}

async function resetDebate() {
  if (state.events) state.events.close();
  state.events = null;
  state.eventsReady = false;
  if (state.debateId) {
    try {
      await requestJson("/api/debates/" + encodeURIComponent(state.debateId) + "/reset", { method: "POST" });
    } catch {
      // The local UI is reset even if the server session has already expired.
    }
  }
  state.debateId = null;
  state.session = null;
  state.activeTurn = null;
  state.liveText = { A: "", B: "", C: "" };
  $("#themeInput").value = "";
  render();
}

async function reconnect() {
  try {
    if (state.debateId) {
      applySession(await requestJson("/api/debates/" + encodeURIComponent(state.debateId)));
      await connectEvents();
      setFooter("接続済み", "サーバーとの接続を確認しました");
    } else {
      await requestJson("/health");
      setFooter("接続済み", "サーバーとの接続を確認しました");
    }
  } catch (error) {
    setFooter("接続エラー", error.message || "サーバーに接続できません");
  }
}

$("#themeForm").addEventListener("submit", startOrNext);
$("#stopButton").addEventListener("click", stopGeneration);
$("#resetButton").addEventListener("click", resetDebate);
$("#reconnectButton").addEventListener("click", reconnect);
$("#closeStageDialogButton").addEventListener("click", () => $("#stageDialog").close());
render();
reconnect();

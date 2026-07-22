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

function messagesForSpeaker(speaker) {
  const messages = (state.session?.messages || []).filter((message) => message.speaker === speaker);
  const liveText = state.liveText[speaker] || "";
  return liveText ? messages.concat([{ kind: "live", text: liveText }]) : messages;
}

function latestMessageOfKind(speaker, kind) {
  const messages = state.session?.messages || [];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].speaker === speaker && messages[index].kind === kind) return messages[index];
  }
  return null;
}

const SPEAKER_LABELS = {
  A: "A 賛成側",
  B: "B 反対側",
  C: "C ファシリテーター",
};

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
  document.querySelectorAll(".role-detail-button").forEach((button) => {
    button.disabled = messagesForSpeaker(button.dataset.speaker).length === 0;
  });

  if (!state.session) {
    $("#bodyC").innerHTML = '<p class="empty-state">テーマを入力すると、整理結果が表示されます。</p>';
    return;
  }
  const cText = state.liveText.C || latestMessage("C")?.text || "";
  const context = state.session.theme_context || {};
  const current = context.current_issue || context.evaluation_axes || context.motion ||
    context.definitions || "テーマから論点を抽出しています。";
  const activeSpeaker = state.session.current_speaker;
  const activeKind = state.session.current_kind;
  const next = activeSpeaker && activeKind
    ? activeSpeaker + "に" + TURN_LABELS[activeKind] + "をお願いします。"
    : state.session.status === "finished"
      ? "ディベートが終了しました。"
      : (context.next_instruction || nextInstruction());
  const speech = cText
    ? '<div class="c-section c-speech"><h3>ファシリテーターの発言</h3><div class="c-box c-speech-box">' +
      escapeHtml(cText) + "</div></div>"
    : "";
  $("#bodyC").innerHTML = speech +
    '<div class="c-section"><h3>現在の論点</h3><div class="c-box">' +
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
  $("#summaryButton").classList.toggle("hidden", !finished);
  renderSurveyAction();
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

function renderSurveyAction() {
  const button = $("#surveyActionButton");
  const session = state.session;
  if (!button || !session || session.status !== "finished") {
    if (button) button.classList.add("hidden");
    return;
  }
  button.classList.remove("hidden");
  button.disabled = false;
  if (session.reference_status === "generating" || session.survey_status === "analyzing") {
    button.textContent = "処理中…";
    button.disabled = true;
  } else if (session.reference_status !== "uploaded") {
    button.textContent = session.reference_status === "error" ? "参照資料を再生成" : "参照資料を生成";
  } else if (session.survey_status === "not_started") {
    button.textContent = "回答受付開始";
  } else if (session.survey_status === "collecting") {
    button.textContent = "回答を取得・分析";
  } else if (session.survey_status === "completed") {
    button.textContent = "分析結果を表示";
  } else {
    button.textContent = "回答分析を再試行";
  }
}

function render() {
  renderControls();
  renderRolePanels();
  renderTimeline();
}

function openMessageDialog(speaker) {
  const dialog = $("#messageDialog");
  const content = $("#messageDialogContent");
  const messages = messagesForSpeaker(speaker);
  $("#messageDialogTitle").textContent = (SPEAKER_LABELS[speaker] || speaker) + " 発言全文";
  content.innerHTML = messages.length
    ? messages.map((message, index) => {
      const label = TURN_LABELS[message.kind] || (message.kind === "live" ? "生成中" : "発言");
      return '<article class="message-entry"><div class="message-entry-heading"><strong>' +
        escapeHtml(label) + '</strong><span>第' + (index + 1) + '発言</span></div><p class="message-entry-text">' +
        escapeHtml(message.text || "") + "</p></article>";
    }).join("")
    : '<p class="empty-state">まだ発言はありません。</p>';
  dialog.showModal();
}

function openSummaryDialog() {
  const aMessage = latestMessageOfKind("A", "closing") || latestMessage("A");
  const bMessage = latestMessageOfKind("B", "closing") || latestMessage("B");
  const cMessage = latestMessageOfKind("C", "summary") || latestMessage("C");
  $("#stageDialog .dialog-heading h2").textContent = "ファシリテーターの最終整理";
  const reference = state.session?.reference_data || {};
  const claims = ["A", "B"].map((speaker) => {
    const items = reference.claims?.[speaker] || [];
    return '<div class="summary-box"><h4>' + speaker + (speaker === "A" ? " 賛成側" : " 反対側") + "の論点</h4>" +
      (items.length ? items.map((claim) => '<p><strong>' + escapeHtml(claim.id || speaker) + " " +
        escapeHtml(claim.title || "") + "</strong><br>" + escapeHtml(claim.summary || "") +
        (claim.basis ? "<br><small>根拠・具体例: " + escapeHtml(claim.basis) + "</small>" : "") +
        "</p>").join("") : '<p class="empty-state">参照資料はまだ生成されていません。</p>') +
      "</div>";
  }).join("");
  const referenceLink = state.session?.reference_drive?.url
    ? '<a class="drive-link" target="_blank" rel="noopener" href="' + escapeHtml(state.session.reference_drive.url) + '">Google Driveで参照資料を開く</a>'
    : "";
  $("#stageContent").innerHTML =
    '<p class="summary-dialog-intro">アンケート回答の前に、A・Bの最終主張と、Cによる最終整理を確認してください。</p>' +
    '<div class="summary-grid">' +
    claims +
    '<div class="summary-box"><h4>A 賛成側の最終主張</h4><p>' + escapeHtml(aMessage?.text || "未生成") + "</p></div>" +
    '<div class="summary-box"><h4>B 反対側の最終主張</h4><p>' + escapeHtml(bMessage?.text || "未生成") + "</p></div>" +
    '<div class="summary-box"><h4>C ファシリテーターの最終整理</h4><p>' + escapeHtml(cMessage?.text || "未生成") + "</p></div>" +
    '</div><p class="summary-dialog-note">必要であれば、各パネルの「全文」から過去の発言も確認できます。</p>' +
    '<div class="section-footer"><span class="button-hint">資料を保存してから回答受付を開始します。</span>' + referenceLink + '</div>';
  $("#stageDialog").showModal();
}

function openAnalysisDialog() {
  const analysis = state.session?.survey_analysis || {};
  const rows = (analysis.questions || []).map((question) =>
    '<article class="analysis-question"><h4>' + escapeHtml(question.question || "") +
    "</h4><p>回答数: " + escapeHtml(question.answered || 0) + "</p><ul>" +
    (question.distribution || []).map((item) => '<li><span>' + escapeHtml(item.value || "") +
      "</span><strong>" + escapeHtml(item.count || 0) + "人（" + escapeHtml(item.percentage || 0) +
      "%）</strong></li>").join("") + "</ul></article>"
  ).join("");
  const reportLink = state.session?.survey_drive?.url
    ? '<a class="drive-link" target="_blank" rel="noopener" href="' + escapeHtml(state.session.survey_drive.url) + '">Google Driveで分析レポートを開く</a>'
    : "";
  $("#stageDialog .dialog-heading h2").textContent = "アンケート分析結果";
  $("#stageContent").innerHTML =
    '<p class="summary-dialog-intro">集計値はサーバーで計算し、Cはその結果を解釈しています。</p>' +
    '<div class="analysis-list">' + (rows || '<p class="empty-state">分析結果はまだありません。</p>') + "</div>" +
    (analysis.interpretation ? '<div class="summary-box analysis-interpretation"><h4>Cによる分析</h4><p>' +
      escapeHtml(analysis.interpretation) + "</p></div>" : "") +
    '<div class="section-footer">' + reportLink + "</div>";
  $("#stageDialog").showModal();
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
  if ([
    "reference_started", "reference_ready", "reference_completed", "reference_error",
    "survey_started", "survey_analysis_started", "survey_aggregated",
    "survey_analysis_completed", "survey_analysis_error",
  ].includes(event.type)) {
    if (payload.state) applySession(payload.state);
    if (event.type.endsWith("error")) {
      setFooter("エラー", payload.message || state.session?.survey_error || "アンケート処理に失敗しました");
    }
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

async function runSurveyAction() {
  if (!state.debateId || !state.session || state.session.status !== "finished") return;
  const session = state.session;
  try {
    if (session.reference_status !== "uploaded") {
      await requestJson("/api/debates/" + encodeURIComponent(state.debateId) + "/reference", { method: "POST" });
      setFooter("参照資料を生成中", "Google Driveへ保存しています…", true);
    } else if (session.survey_status === "not_started") {
      applySession(await requestJson("/api/debates/" + encodeURIComponent(state.debateId) + "/survey/start", { method: "POST" }));
      setFooter("回答受付中", "参照資料を確認してGoogle Formへ回答してください");
      if (state.session.reference_drive?.url) window.open(state.session.reference_drive.url, "_blank", "noopener");
    } else if (session.survey_status === "collecting") {
      await requestJson("/api/debates/" + encodeURIComponent(state.debateId) + "/survey/analyze", { method: "POST" });
      setFooter("アンケート分析中", "回答を取得してCが分析しています…", true);
    } else if (session.survey_status === "completed") {
      openAnalysisDialog();
    } else {
      await requestJson("/api/debates/" + encodeURIComponent(state.debateId) + "/survey/analyze", { method: "POST" });
      setFooter("アンケート分析中", "回答を取得してCが分析しています…", true);
    }
  } catch (error) {
    setFooter("処理エラー", error.message || "アンケート処理に失敗しました");
  }
}

$("#themeForm").addEventListener("submit", startOrNext);
$("#stopButton").addEventListener("click", stopGeneration);
$("#resetButton").addEventListener("click", resetDebate);
$("#reconnectButton").addEventListener("click", reconnect);
$("#summaryButton").addEventListener("click", openSummaryDialog);
$("#surveyActionButton").addEventListener("click", runSurveyAction);
$("#closeStageDialogButton").addEventListener("click", () => $("#stageDialog").close());
document.querySelectorAll(".role-detail-button").forEach((button) => {
  button.addEventListener("click", () => openMessageDialog(button.dataset.speaker));
});
$("#closeMessageDialogButton").addEventListener("click", () => $("#messageDialog").close());
render();
reconnect();

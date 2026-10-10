// CR·PR 의사결정 에이전트 — 화면 로직 (프레임워크 없음)
"use strict";

const $app = document.getElementById("app");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const AREAS = [["SCORE_REG", "규제"], ["SCORE_FIN", "재무"], ["SCORE_PR", "여론"], ["SCORE_LEG", "법무"], ["SCORE_OPP", "기회"]];
const STAGE_LABEL = { ingested: "접수", classifying: "분류 중", gate1: "게이트1 분류 확정", analyzing: "분석 중",
  review: "담당자 검수", decision: "게이트2 조직장 판단", decided: "결정 완료", error: "오류" };
const LEVEL_ORDER = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
let pollTimer = null;
let CODEBOOK = null;

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}
function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), 3500);
}
const lv = (l) => (l ? `<span class="lv lv-${esc(l)}">${esc(l)}</span>` : `<span class="chip">미평가</span>`);
const dday = (d) => (d === null || d === undefined ? "" : `<span class="${d <= 3 ? "dd-hot" : ""}">${d < 0 ? "D+" + -d : d === 0 ? "D-Day" : "D-" + d}</span>`);
const stage = (s) => `<span class="chip ${s === "error" ? "warn" : s === "decided" ? "ok" : ""}">${esc(STAGE_LABEL[s] || s)}</span>`;
const sortRecs = (rs) => rs.slice().sort((a, b) =>
  (LEVEL_ORDER[a.RISK_LEVEL] ?? 9) - (LEVEL_ORDER[b.RISK_LEVEL] ?? 9) || (a.D_DAY ?? 999) - (b.D_DAY ?? 999));

function recTable(rows) {
  if (!rows.length) return `<p class="muted">기록이 없습니다.</p>`;
  return `<div class="tablewrap"><table class="t"><tr><th>등급</th><th>DOC_ID</th><th>제목</th><th>ISSUE</th><th>점수</th><th>보고 Level</th><th>상태</th><th>단계</th><th>기한</th></tr>
  ${rows.map((r) => `<tr class="click" data-doc="${esc(r.DOC_ID)}"><td>${lv(r.RISK_LEVEL)}</td><td class="small">${esc(r.DOC_ID)}</td>
  <td>${esc(r.DOC_TITLE)}</td><td>${esc(r.ISSUE_ID || "")}</td><td>${esc(r.TOTAL_RISK_SCORE ?? "")}${r.SCORE_OPP ? ` <span class="muted small">기회 ${r.SCORE_OPP}</span>` : ""}</td>
  <td>${esc(r.DECISION_TYPE || "")}</td><td>${esc(r.STATUS)}</td><td>${stage(r.STAGE)}</td><td>${dday(r.D_DAY)}</td></tr>`).join("")}</table></div>`;
}
function bindRows() {
  $app.querySelectorAll("tr[data-doc]").forEach((tr) => tr.addEventListener("click", () => (location.hash = "#/doc/" + tr.dataset.doc)));
}
function bars(obj, keys) {
  const max = Math.max(1, ...Object.values(obj));
  return (keys || Object.keys(obj)).map((k) => `<div class="barrow"><span>${esc(k)}</span><div class="bar" style="width:${((obj[k] || 0) / max) * 100}%;${LEVEL_ORDER[k] !== undefined ? `background:var(--${["crit", "high", "med", "low"][LEVEL_ORDER[k]]})` : ""}"></div><b>${obj[k] || 0}</b></div>`).join("");
}

// ------------------------------------------------------------ 대시보드
async function viewDashboard() {
  const [d, recs] = await Promise.all([api("/api/dashboard"), api("/api/records")]);
  const hot = (d.by_level.CRITICAL || 0) + (d.by_level.HIGH || 0);
  const gates = d.alerts.filter((a) => a.reasons.some((x) => x.startsWith("게이트") || x.startsWith("담당자"))).length;
  $app.innerHTML = `<h2>대시보드</h2>
  <div class="grid g4">
    <div class="card tile"><div class="num">${d.open}</div><div class="lab">진행 중 이슈 (전체 ${d.total})</div></div>
    <div class="card tile"><div class="num" style="color:var(--crit)">${hot}</div><div class="lab">CRITICAL·HIGH</div></div>
    <div class="card tile"><div class="num">${gates}</div><div class="lab">게이트·검수 대기</div></div>
    <div class="card tile"><div class="num">${d.adoption_rate === null ? "—" : Math.round(d.adoption_rate * 100) + "%"}</div><div class="lab">추천안 채택률 (목표 70%)</div></div>
  </div>
  <div class="grid g2">
    <div class="card"><h3 style="margin-top:0">알림 — D-Day·대기</h3>${d.alerts.length ? `<table class="t">${d.alerts.slice(0, 12).map((a) =>
      `<tr class="click" data-doc="${esc(a.DOC_ID)}"><td>${lv(a.RISK_LEVEL)}</td><td>${esc(a.DOC_TITLE)}</td><td>${a.reasons.map((x) => `<span class="chip warn">${esc(x)}</span>`).join(" ")}</td><td>${dday(a.D_DAY)}</td></tr>`).join("")}</table>` : `<p class="muted">알림 없음</p>`}</div>
    <div class="card"><h3 style="margin-top:0">진행 중 — 등급별</h3>${bars(d.by_level, ["CRITICAL", "HIGH", "MEDIUM", "LOW"])}
      <h3>조직장 결정</h3>${bars(d.decisions, ["승인", "수정 채택", "기각"])}
      <h3>L1 분포</h3>${bars(d.by_l1)}<h3>월별 유입</h3>${bars(d.by_month)}</div>
  </div>
  <div class="card"><h3 style="margin-top:0">진행 중 이슈 (등급·D-Day 순)</h3>${recTable(sortRecs(recs.filter((r) => r.STATUS !== "종결")).slice(0, 20))}
  <div class="btns"><a href="/api/export.xlsx"><button class="ghost">운영 워크북(엑셀) 내려받기</button></a><button class="ghost" id="inbox">inbox 폴더 처리</button></div></div>`;
  bindRows();
  document.getElementById("inbox").onclick = async () => {
    const r = await api("/api/inbox", {}); toast(`inbox ${r.length}건 처리`); viewDashboard();
  };
}

// ------------------------------------------------------------ 문서 접수
async function viewNew() {
  CODEBOOK = CODEBOOK || (await api("/api/codebook"));
  $app.innerHTML = `<h2>문서 접수</h2><div class="card">
  <div class="row"><div><label>출처유형</label><select id="src">${CODEBOOK.source_types.map((s) => `<option>${s}</option>`).join("")}</select></div>
  <div style="flex:2"><label>문서 제목 (비우면 파일명/첫 줄)</label><input id="title"></div></div>
  <label>파일 (PDF · HWPX · HWP · DOCX · HTML · TXT)</label><input type="file" id="file" accept=".pdf,.hwpx,.hwp,.docx,.html,.htm,.txt,.md">
  <label>또는 본문 붙여넣기 (기사·공문 텍스트)</label><textarea id="text" style="min-height:200px"></textarea>
  <label>원문 참조 (URL 등, 선택)</label><input id="ref">
  <div class="btns"><button id="go">접수하고 분석 시작</button></div>
  <p class="muted small">이름·연락처·주민번호·이메일·계좌번호는 전송 전에 자동으로 가려집니다. 분류 신뢰도가 0.7 미만이면 담당자 분류 확정(게이트 1)에서 멈춥니다.</p></div>`;
  document.getElementById("go").onclick = async (ev) => {
    const f = document.getElementById("file").files[0];
    const body = { source_type: src.value, title: title.value, text: text.value, source_ref: ref.value };
    if (f) {
      body.filename = f.name;
      body.file_b64 = await new Promise((res) => { const r = new FileReader(); r.onload = () => res(r.result.split(",")[1]); r.readAsDataURL(f); });
    } else if (!text.value.trim()) return toast("파일을 고르거나 본문을 붙여넣어 주세요.");
    ev.target.disabled = true;
    try { const r = await api("/api/ingest", body); location.hash = "#/doc/" + r.doc_id; }
    catch (e) { toast(e.message); ev.target.disabled = false; }
  };
}

// ------------------------------------------------------------ 목록
async function viewList() {
  const recs = await api("/api/records");
  $app.innerHTML = `<h2>Decision Log</h2><div class="card"><div class="row">
   <div><label>상태</label><select id="fs"><option value="">전체</option><option>신규접수</option><option>분석완료</option><option>대응중</option><option>종결</option></select></div>
   <div><label>등급</label><select id="fl"><option value="">전체</option><option>CRITICAL</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select></div>
   <div style="flex:2"><label>검색</label><input id="fq" placeholder="제목·ISSUE_ID"></div></div><div id="tbl"></div></div>`;
  const draw = () => {
    const s = fs.value, l = fl.value, q = fq.value.trim();
    document.getElementById("tbl").innerHTML = recTable(sortRecs(recs.filter((r) => (!s || r.STATUS === s) && (!l || r.RISK_LEVEL === l)
      && (!q || (r.DOC_TITLE + " " + (r.ISSUE_ID || "")).includes(q)))));
    bindRows();
  };
  [fs, fl, fq].forEach((el) => el.addEventListener("input", draw)); draw();
}

// ------------------------------------------------------------ 상세
const STEP_FLOW = ["ingested", "gate1", "analyzing", "review", "decision", "decided"];
function steps(cur) {
  const idx = STEP_FLOW.indexOf(cur === "classifying" ? "ingested" : cur);
  return `<div class="steps">${["접수·분류", "게이트1 분류 확정", "리스크·의사결정 합성", "담당자 검수", "게이트2 조직장 판단", "배포·실행"]
    .map((n, i) => `<span class="${i < idx ? "done" : i === idx ? "cur" : ""}">${n}</span>`).join("")}</div>`;
}

async function viewDoc(id) {
  const [r, tax] = await Promise.all([api("/api/records/" + id), api("/api/taxonomy")]);
  CODEBOOK = CODEBOOK || (await api("/api/codebook"));
  const busy = ["ingested", "classifying", "analyzing"].includes(r.STAGE);
  let action = "";
  if (busy) action = `<div class="notice"><span class="spin"></span> ${esc(STAGE_LABEL[r.STAGE])} — sub-agent 가 작업 중입니다. 화면이 자동으로 갱신됩니다.</div>`;
  else if (r.STAGE === "error") action = `<div class="notice err"><b>처리 오류</b><pre>${esc(r.ERROR)}</pre>
     <div class="btns"><button data-rerun="analyze">분석 단계부터 재실행</button><button class="ghost" data-rerun="classify">분류부터 재실행</button></div></div>`;
  else if (r.STAGE === "gate1") action = gate1Form(r, tax);
  else if (r.STAGE === "review") action = reviewForm(r);
  else if (r.STATUS === "분석완료") action = decideForm(r);
  else if (r.STATUS === "대응중") action = `<div class="card"><h3 style="margin-top:0">종결 처리</h3><label>결과·교훈 (다음 유사 사안 분석에 「과거 사례」로 투입됩니다)</label><textarea id="lessons"></textarea>
     <div class="row"><div><label>처리자</label><input id="closer"></div></div><div class="btns"><button id="closebtn">종결</button></div></div>`;

  const v = r.VALIDATION_JSON, loop = r.LOOP_LOG;
  $app.innerHTML = `<p><a href="#/list">← Decision Log</a></p>
  <div class="card"><div class="row" style="align-items:center"><div style="flex:3"><h2 style="margin:0">${esc(r.DOC_TITLE)}</h2>
   <div class="muted small">${esc(r.DOC_ID)} · ${esc(r.SOURCE_TYPE)} · ${esc(r.label || "분류 전")} · 접수 ${esc((r.UPLOAD_DATE || "").replace("T", " "))}</div></div>
   <div style="text-align:right">${lv(r.RISK_LEVEL)} ${stage(r.STAGE)} <span class="chip">${esc(r.STATUS)}</span> ${dday(r.D_DAY)}</div></div>
   ${steps(r.STATUS === "대응중" || r.STATUS === "종결" ? "decided" : r.STAGE)}
   ${r.MASKED && r.MASKED.counts && Object.keys(r.MASKED.counts).length ? `<div class="notice warn small">민감정보 마스킹: ${esc(Object.entries(r.MASKED.counts).map(([k, n]) => k + " " + n + "건").join(", "))}</div>` : ""}
   ${(r.MASKED && r.MASKED.warnings || []).map((w) => `<div class="notice warn small">${esc(w)}</div>`).join("")}
  </div>
  ${action}
  ${r.report_html ? `<div class="card"><div class="row" style="align-items:center"><h3 style="margin:0">원페이지 의사결정 보고서</h3>
     <div style="text-align:right"><a href="/api/records/${esc(r.DOC_ID)}/report.html" target="_blank"><button class="ghost">인쇄용 보기</button></a>
     <a href="/api/records/${esc(r.DOC_ID)}/report.docx"><button class="ghost">Word</button></a></div></div>
     <div class="report-frame">${r.report_html}</div></div>` : ""}
  ${loop ? `<div class="card"><h3 style="margin-top:0">품질 루프 ${loop.converged ? `<span class="chip ok">수렴</span>` : `<span class="chip warn">미수렴 — 검수 시 확인</span>`}</h3>
     ${loop.attempts.map((a) => `<details ${a.validator_errors.length || (a.critic && !a.critic.passed) ? "open" : ""}><summary>시도 ${a.attempt + 1}: 구조 검증 ${a.validator_errors.length ? "실패 " + a.validator_errors.length + "건" : "통과"}${a.critic ? ` · critic ${a.critic.passed ? "통과" : "지적 " + a.critic.issues.length + "건"}` : ""}</summary>
       <ul class="small">${a.validator_errors.map((e) => `<li>${esc(e)}</li>`).join("")}${(a.critic ? a.critic.issues : []).map((i) => `<li>[${esc(i.type)}] ${esc(i.field)} — ${esc(i.problem)}</li>`).join("")}</ul></details>`).join("")}
     ${v && v.warnings.length ? `<h3>검수 시 확인할 경고</h3><ul class="small">${v.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}</div>` : ""}
  ${r.CLASSIFICATION_JSON ? `<details class="card"><summary>분류 근거 · 원문 · 감사 로그</summary>
     <h3>분류</h3><pre>${esc(JSON.stringify(r.CLASSIFICATION_JSON, null, 1))}</pre>
     <h3>원문 (마스킹 적용본)</h3><pre>${esc(r.SOURCE_TEXT)}</pre>
     <h3>감사 로그</h3><div class="tablewrap"><table class="t"><tr><th>단계</th><th>모델</th><th>Prompt</th><th>시도</th><th>토큰</th><th>시각</th></tr>
     ${r.audit.map((a) => `<tr><td>${esc(a.step)}</td><td>${esc(a.model)}</td><td class="small">${esc(a.prompt_version)}</td><td>${a.attempt + 1}</td><td class="small">${esc(a.usage)}</td><td class="small">${esc(a.at)}</td></tr>`).join("")}</table></div>
     <p class="small muted">PROMPT ${esc(r.PROMPT_VERSION || "")} · MODEL ${esc(r.MODEL_VERSION || "")} · 생성 ${esc(r.LEAD_SECONDS ?? "")}초</p></details>` : ""}`;

  bindDoc(r);
  if (busy) pollTimer = setTimeout(() => route(), 3000);
}

function gate1Form(r, tax) {
  const cl = r.CLASSIFICATION_JSON || {};
  const opts = tax.issues.filter((i) => i.status === "active").map((i) => `<option value="${esc(i.issue_id)}" ${i.issue_id === r.ISSUE_ID ? "selected" : ""}>${esc(i.label)}</option>`).join("");
  return `<div class="card"><h3 style="margin-top:0">게이트 1 — 담당자 분류 확정</h3>
   <div class="notice warn">분류 신뢰도 ${esc(r.CLASS_CONFIDENCE)} ${r.NEW_CATEGORY_CANDIDATE ? ` · 신규 분류 후보: <b>${esc(r.NEW_CATEGORY_CANDIDATE)}</b> (분류체계 화면에서 세분류를 추가할 수 있습니다)` : ""}</div>
   <p class="small">근거: ${(cl.evidence || []).map((e) => "「" + esc(e) + "」").join(" ") || "—"}</p>
   <p class="small muted">키워드 엔진 후보: ${(cl.keyword_candidates || []).map((k) => esc(k.issue_id) + "(" + k.score + ")").join(", ") || "없음"}</p>
   <label>주 코드</label><select id="g1issue">${opts}</select>
   <label>부 코드 (최대 2개, Ctrl 클릭)</label><select id="g1sub" multiple size="4">${opts.replace(/ selected/g, "")}</select>
   <div class="row"><div><label>담당자</label><input id="g1actor"></div><div style="flex:2"><label>수정 사유 (코드를 바꾼 경우)</label><input id="g1reason"></div></div>
   <div class="btns"><button id="g1go">분류 확정 → 분석 진행</button></div></div>`;
}

function reviewForm(r) {
  const panel = r.PANEL_JSON || {};
  const actions = (r.REPORT_JSON && r.REPORT_JSON.action_plan) || [];
  return `<div class="card"><h3 style="margin-top:0">담당자 검수 — 점수 보정 · 실명 지정</h3>
   <p class="small muted">에이전트 점수를 조정하면 조정 전·후 값과 사유가 저장되고, 월간 피드백 루프에서 L3 Prompt 의 편향을 찾는 데 쓰입니다. 종합 점수·등급은 시스템 수식으로 다시 계산됩니다.</p>
   <div class="scoregrid">${AREAS.map(([k, n]) => `<div><label>${n} (에이전트 ${esc(r[k])})</label><select data-score="${k}">${[1, 2, 3, 4, 5].map((x) => `<option ${x === r[k] ? "selected" : ""}>${x}</option>`).join("")}</select>
     <input data-reason="${k}" placeholder="조정 사유" style="margin-top:4px"><div class="small muted">${esc((panel[k] || {}).summary || "")}</div></div>`).join("")}</div>
   <h3>Action 담당자 실명</h3><div class="row">${actions.map((a) => `<div><label>${esc(a.when)} — ${esc(a.task)}</label><input data-owner="${esc(a.when)}" value="${esc(a.owner)}"></div>`).join("")}</div>
   <label>검수 메모 (추정·확인 필요 항목 검증 결과, 보완한 수치 등)</label><textarea id="rvnote"></textarea>
   <div class="row"><div><label>검수자</label><input id="rvname" value="${esc(r.REVIEWER || "")}"></div></div>
   <div class="btns"><button id="rvgo">검수 완료 → 조직장 판단 요청</button><button class="ghost" data-rerun="analyze">다시 분석</button></div></div>`;
}

function decideForm(r) {
  return `<div class="card"><h3 style="margin-top:0">게이트 2 — 조직장 판단</h3>
   <div class="notice">에이전트 추천: <b>${esc(r.AGENT_RECOMMENDATION)}</b><br>제안 보고 Level: <b>${esc(r.DECISION_TYPE)}</b> · 종합 ${esc(r.TOTAL_RISK_SCORE)}점 ${esc(r.RISK_LEVEL)} · 기회 ${esc(r.SCORE_OPP)}</div>
   <div class="row"><div><label>결정</label><select id="dcd">${CODEBOOK.final_decisions.map((x) => `<option>${x}</option>`).join("")}</select></div>
   <div><label>보고 Level 확정</label><select id="dtype">${CODEBOOK.report_levels.map((x) => `<option ${x === r.DECISION_TYPE ? "selected" : ""}>${x}</option>`).join("")}</select></div>
   <div><label>결정자</label><input id="dname"></div></div>
   <label>최종 결정 내용 (수정 채택 시 수정안, 비우면 에이전트 추천안)</label><textarea id="dtext"></textarea>
   <label>사유</label><input id="dreason">
   <div class="btns"><button id="dgo">판단 기록 → 배포</button></div></div>`;
}

function bindDoc(r) {
  const id = r.DOC_ID;
  $app.querySelectorAll("[data-rerun]").forEach((b) => (b.onclick = async () => { await api(`/api/records/${id}/rerun`, { step: b.dataset.rerun }); route(); }));
  const g1 = document.getElementById("g1go");
  if (g1) g1.onclick = async () => {
    if (!g1actor.value.trim()) return toast("담당자 이름을 입력하세요.");
    const sub = [...g1sub.selectedOptions].map((o) => o.value).filter((x) => x !== g1issue.value).slice(0, 2);
    try { await api(`/api/records/${id}/confirm`, { issue_id: g1issue.value, sub_ids: sub, actor: g1actor.value, reason: g1reason.value }); route(); } catch (e) { toast(e.message); }
  };
  const rv = document.getElementById("rvgo");
  if (rv) rv.onclick = async () => {
    if (!rvname.value.trim()) return toast("검수자 이름을 입력하세요.");
    const scores = {}, reasons = {}, owners = {};
    $app.querySelectorAll("[data-score]").forEach((s) => (scores[s.dataset.score] = +s.value));
    $app.querySelectorAll("[data-reason]").forEach((s) => (reasons[s.dataset.reason] = s.value));
    $app.querySelectorAll("[data-owner]").forEach((s) => (owners[s.dataset.owner] = s.value));
    const changed = AREAS.filter(([k]) => scores[k] !== r[k] && !reasons[k].trim());
    if (changed.length) return toast("점수를 바꾼 항목에는 조정 사유를 적어 주세요: " + changed.map((x) => x[1]).join(", "));
    try { await api(`/api/records/${id}/review`, { reviewer: rvname.value, scores, reasons, owners, note: rvnote.value }); toast("검수 완료"); route(); } catch (e) { toast(e.message); }
  };
  const dg = document.getElementById("dgo");
  if (dg) dg.onclick = async () => {
    if (!dname.value.trim()) return toast("결정자 이름을 입력하세요.");
    if (dcd.value !== "승인" && !dreason.value.trim()) return toast("수정 채택·기각은 사유가 필요합니다.");
    try {
      const res = await api(`/api/records/${id}/decide`, { approver: dname.value, decision: dcd.value, reason: dreason.value, decision_type: dtype.value, final_text: dtext.value });
      toast(`배포: ${res.distribution.to} — ${res.distribution.format} (${res.distribution.when})`); route();
    } catch (e) { toast(e.message); }
  };
  const cb = document.getElementById("closebtn");
  if (cb) cb.onclick = async () => {
    if (!lessons.value.trim() || !closer.value.trim()) return toast("교훈과 처리자를 입력하세요.");
    await api(`/api/records/${id}/close`, { lessons: lessons.value, actor: closer.value }); route();
  };
}

// ------------------------------------------------------------ 분류체계
async function viewTaxonomy() {
  const tax = await api("/api/taxonomy");
  $app.innerHTML = `<h2>분류체계 (Taxonomy Master)</h2>
  <div class="card"><h3 style="margin-top:0">세분류(ISSUE_ID) 추가 — 담당자 권한</h3><div class="row">
   <div><label>L3 소분류</label><select id="tl3">${tax.l3.map((l) => `<option value="${l.code}">${l.code} ${esc(l.name)} (Prompt ${esc(l.prompt)})</option>`).join("")}</select></div>
   <div style="flex:2"><label>이슈명</label><input id="tname"></div><div style="flex:0"><button id="tadd">추가</button></div></div>
   <p class="small muted">L1·L2 변경은 조직장 승인, L3 신설은 운영자(신규 L3 Prompt 작성 + 골든셋 2건 검증) 절차를 따릅니다. 코드는 삭제하지 않고 폐기 상태로만 전환합니다.</p></div>
  <div class="card tablewrap"><table class="t"><tr><th>ISSUE_ID</th><th>분류 경로</th><th>세분류 이슈명</th><th>전문 Prompt</th><th>상태</th><th></th></tr>
   ${tax.issues.map((i) => `<tr><td>${esc(i.issue_id)}</td><td class="small">${esc(i.label.split(" · ")[0].replace(i.issue_id + " ", ""))}</td><td>${esc(i.name)}</td><td>${esc(i.prompt)}</td>
   <td>${i.status === "active" ? `<span class="chip ok">사용</span>` : `<span class="chip">폐기</span>`}</td><td>${i.status === "active" ? `<button class="ghost" data-dep="${esc(i.issue_id)}">폐기</button>` : ""}</td></tr>`).join("")}</table></div>`;
  tadd.onclick = async () => {
    if (!tname.value.trim()) return toast("이슈명을 입력하세요.");
    try { const r = await api("/api/taxonomy/issue", { l3: tl3.value, name: tname.value }); toast(r.issue_id + " 추가"); viewTaxonomy(); } catch (e) { toast(e.message); }
  };
  $app.querySelectorAll("[data-dep]").forEach((b) => (b.onclick = async () => {
    if (!confirm(b.dataset.dep + " 를 폐기 상태로 바꿀까요?")) return;
    await api("/api/taxonomy/deprecate", { issue_id: b.dataset.dep }); viewTaxonomy();
  }));
}

// ------------------------------------------------------------ Prompt
async function viewPrompts() {
  const ps = await api("/api/prompts");
  $app.innerHTML = `<h2>Prompt Registry</h2><p class="muted small">Layer 1 Master → Layer 3 Format → Layer 2 L3 전문 Prompt 순으로 조립됩니다(고정 부분이 앞이라 프롬프트 캐시가 유지됩니다). 파일은 <code>cr_pr_agent/prompts/</code> 에 있고, 개정은 품질·피드백 화면의 골든셋 게이트를 거쳐 배포됩니다.</p>
  ${["Layer 1", "Layer 3", "Layer 2", "Sub-agent"].map((L) => `<div class="card"><h3 style="margin-top:0">${L}</h3>${ps.filter((p) => p.layer === L).map((p) =>
    `<details><summary><b>${esc(p.id)}</b> v${esc(p.version)} ${esc(p.name)} <span class="muted small">${esc(p.applies_to)} · ${esc(p.digest)}</span></summary><pre>${esc(p.body)}</pre></details>`).join("")}</div>`).join("")}`;
}

// ------------------------------------------------------------ 품질·피드백
async function viewQuality() {
  const [ev, fb] = await Promise.all([api("/api/evals"), api("/api/feedback")]);
  const s = fb.stats;
  const pct = (x) => (x === null || x === undefined ? "—" : Math.round(x * 100) + "%");
  $app.innerHTML = `<h2>품질 평가 · 피드백 루프</h2>
  <div class="grid g4">
   <div class="card tile"><div class="num">${pct(s.adoption_rate)}</div><div class="lab">추천안 채택률 · 목표 70%</div></div>
   <div class="card tile"><div class="num">${pct(s.classification_accuracy_l3)}</div><div class="lab">분류 정확도(L3) · 목표 90%</div></div>
   <div class="card tile"><div class="num">${pct(s.score_within1)}</div><div class="lab">점수 ±1 일치도 · 목표 85%</div></div>
   <div class="card tile"><div class="num">${s.avg_lead_seconds ?? "—"}<span class="small">초</span></div><div class="lab">초안 생성 시간 · 목표 30분 이내</div></div></div>
  <div class="card"><h3 style="margin-top:0">월간 피드백 — 개정 대상</h3>
   ${s.targets.length ? `<table class="t">${s.targets.map((t) => `<tr><td>${esc(t.prompt_id)}</td><td>L3 ${esc(t.l3)}</td><td>${esc(t.reason)}</td><td><button class="ghost" data-prop="${esc(t.prompt_id)}">개정안 작성</button></td></tr>`).join("")}</table>`
     : `<p class="muted">체계적 편향이 감지된 L3 가 없습니다. (같은 방향 조정 평균 ±0.75 이상 또는 기각률 30% 이상이면 대상이 됩니다)</p>`}
   ${s.revise_master ? `<div class="notice warn">편향이 3개 이상 Prompt 에 걸쳐 있습니다 — Master Prompt 개정 검토 <button class="ghost" data-prop="MASTER">Master 개정안 작성</button></div>` : ""}
   <h3>개정안 (골든셋 게이트 대기)</h3>${fb.proposals.length ? fb.proposals.map((p) => `<div class="row" style="align-items:center"><span>${esc(p)}</span><span style="flex:0"><button data-promote="${esc(p)}">골든셋 평가 후 배포</button></span></div>`).join("") : `<p class="muted small">없음</p>`}
   <details><summary>리포트 전문</summary><pre>${esc(fb.markdown)}</pre></details></div>
  <div class="card"><div class="row" style="align-items:center"><h3 style="margin:0">골든셋 평가 이력</h3><span style="flex:0;white-space:nowrap"><button class="ghost" data-eval="dev">dev 평가</button> <button class="ghost" data-eval="test">test 평가</button></span></div>
   ${ev.length ? `<div class="tablewrap"><table class="t"><tr><th>#</th><th>시각</th><th>split</th><th>n</th><th>종합</th><th>분류</th><th>점수±1</th><th>핵심사실</th><th>완결성</th><th>추천 일치</th><th>환각</th></tr>
   ${ev.map((e) => `<tr><td>${e.id}</td><td class="small">${esc(e.at)}</td><td>${esc(e.split)}</td><td>${e.summary.n}</td><td><b>${e.summary.score}</b></td><td>${pct(e.summary.l3_match)}</td><td>${pct(e.summary.score_within1)}</td><td>${pct(e.summary.key_fact_recall)}</td><td>${pct(e.summary.complete)}</td><td>${pct(e.summary.recommendation_match)}</td><td>${e.summary.hallucinations}</td></tr>`).join("")}</table></div>` : `<p class="muted">평가 기록이 없습니다.</p>`}</div>`;
  $app.querySelectorAll("[data-prop]").forEach((b) => (b.onclick = async () => {
    b.disabled = true; try { const r = await api("/api/feedback/propose", { prompt_id: b.dataset.prop }); toast(r.proposal + " 작성"); viewQuality(); } catch (e) { toast(e.message); b.disabled = false; }
  }));
  $app.querySelectorAll("[data-promote]").forEach((b) => (b.onclick = async () => {
    b.disabled = true; b.textContent = "평가 중…";
    try { const r = await api("/api/feedback/promote", { proposal: b.dataset.promote }); toast(r.promoted ? `배포됨 (${r.baseline.score} → ${r.candidate.score})` : `보류: ${r.note || `점수 ${r.baseline.score} → ${r.candidate.score}`}`); viewQuality(); }
    catch (e) { toast(e.message); b.disabled = false; }
  }));
  $app.querySelectorAll("[data-eval]").forEach((b) => (b.onclick = async () => { await api("/api/evals/run", { split: b.dataset.eval }); toast("평가를 시작했습니다. 잠시 후 새로고침하세요."); }));
}

// ------------------------------------------------------------ 라우터
async function route() {
  clearTimeout(pollTimer);
  const h = location.hash.replace(/^#\/?/, "");
  const [r, arg] = h.split("/");
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("on", a.dataset.r === (r === "doc" ? "list" : r)));
  try {
    if (r === "new") await viewNew();
    else if (r === "list") await viewList();
    else if (r === "doc") await viewDoc(arg);
    else if (r === "taxonomy") await viewTaxonomy();
    else if (r === "prompts") await viewPrompts();
    else if (r === "quality") await viewQuality();
    else await viewDashboard();
  } catch (e) { $app.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; }
}
window.addEventListener("hashchange", route);
api("/api/status").then((s) => {
  document.getElementById("mode").innerHTML = s.mode === "offline"
    ? `<b class="off">오프라인 모의 모드</b> — API 키 설정 시 실제 분석`
    : `${esc(s.mode)} · 판단 ${esc(s.heavy_model)} · 경량 ${esc(s.light_model)}`;
});
route();

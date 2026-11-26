const state = {
  framework:      "SOC 2",
  orgName:        "",
  assignee:       "",
  employeeCount:  null,
  mode:           "risk",          // "risk" | "gap"
  phase:          "employee_count",
  questions:      [],
  currentIndex:   0,
  currentSection: null,            // tracks section changes for gap banners
  followUpCount:  0,
  controlHistory: [],
  results:        [],
  gapResults:     [],
  isProcessing:   false,
  pendingStart:   false,
  finished:       false            // true once Skip to end has run; stops the interview loop
};

// ── SETUP ──────────────────────────────────────────────

document.querySelectorAll(".framework-option input[type=radio]").forEach(radio => {
  radio.addEventListener("change", () => {
    state.framework = radio.value;
  });
});

// Mode toggle
document.querySelectorAll(".mode-btn").forEach(btn => {
  btn.addEventListener("click", () => setMode(btn.dataset.mode));
});

function setMode(mode) {
  state.mode = mode;

  document.querySelectorAll(".mode-btn").forEach(btn =>
    btn.classList.toggle("active", btn.dataset.mode === mode)
  );

  const soc2Radio  = document.querySelector(".framework-option input[value='SOC 2']");
  const soc2Badge  = document.querySelector(".framework-option[data-framework='SOC 2'] .coming-soon-badge");

  if (mode === "gap") {
    soc2Radio.disabled = true;
    soc2Badge.style.display = "inline";
    // auto-select ISO 27001 if SOC 2 was selected
    if (state.framework === "SOC 2") {
      document.querySelector(".framework-option input[value='ISO 27001']").checked = true;
      state.framework = "ISO 27001";
    }
    document.getElementById("hero-title").innerHTML =
      'Know your <span>compliance gaps</span> before your <span>auditor does.</span>';
    document.getElementById("hero-body-1").textContent =
      "Turn a structured compliance interview into a clear gap register, practical remediation plan, and audit-ready report.";
  } else {
    soc2Radio.disabled = false;
    soc2Badge.style.display = "none";
    document.getElementById("hero-title").innerHTML =
      'Know your <span>risk posture</span> before your <span>auditor does.</span>';
    document.getElementById("hero-body-1").textContent =
      "Turn a structured compliance interview into a clear risk register, practical treatment plan, and audit-ready report.";
  }
}

document.getElementById("start-btn").addEventListener("click", showInstructions);

// Render the sign-in / sign-out button in the form panel header
function renderAuthHeaderBtn() {
  const el = document.getElementById("auth-header-btn");
  if (!el) return;
  if (window.USER_EMAIL) {
    el.innerHTML = `
      <span class="auth-user-email">${escapeHtml(window.USER_EMAIL)}</span>
      <a href="/logout" class="auth-signout-link">Sign out</a>`;
  } else {
    el.innerHTML = `<button class="sign-in" onclick="openAuthModal('login')">Sign In</button>`;
  }
}
renderAuthHeaderBtn();

function showInstructions() {
  if (!window.USER_EMAIL) {
    state.pendingStart = true;
    openAuthModal('login');
    return;
  }
  const orgName = document.getElementById("org-name").value.trim();
  if (!orgName) { showSetupError("Please enter your organisation name."); return; }
  document.getElementById("setup-error").style.display = "none";
  document.getElementById("instructions-backdrop").style.display = "flex";
}

function closeInstructions(proceed) {
  document.getElementById("instructions-backdrop").style.display = "none";
  if (proceed) startAssessment();
}

function handleInstructionsBackdrop(e) {
  if (e.target === document.getElementById("instructions-backdrop")) closeInstructions(true);
}

async function startAssessment() {
  const orgName  = document.getElementById("org-name").value.trim();
  const assignee = document.getElementById("assignee").value.trim();

  state.orgName  = orgName;
  state.assignee = assignee;
  state.results        = [];
  state.gapResults     = [];
  state.currentSection = null;
  state.finished       = false;
  document.getElementById("skip-btn").style.display = "";

  const btn = document.getElementById("start-btn");
  btn.textContent = "Loading…";
  btn.disabled    = true;

  try {
    const endpoint = state.mode === "gap"
      ? `/api/gap-questions/${encodeURIComponent(state.framework)}`
      : `/api/questions/${encodeURIComponent(state.framework)}`;
    const res = await fetch(endpoint);
    state.questions = await res.json();
  } catch {
    showSetupError("Failed to load questions. Is the server running?");
    btn.textContent = "Begin assessment";
    btn.disabled    = false;
    return;
  }

  document.getElementById("setup-screen").style.display = "none";
  document.getElementById("chat-screen").style.display  = "flex";
  const topbarLabel = state.mode === "gap" ? `${state.framework} Gap Assessment` : state.framework;
  document.getElementById("sb-framework").textContent   = topbarLabel;
  document.getElementById("sb-org").textContent         = state.orgName;

  updateProgress();

  if (state.mode === "gap") {
    state.phase = "assessment";   // gap mode has no employee-count step
    addBotMessage(
      `Welcome. I'll be your <strong>${escapeHtml(state.framework)}</strong> gap analyst for ` +
      `<strong>${escapeHtml(state.orgName)}</strong> today. We have <strong>${state.questions.length} controls</strong> ` +
      `to work through across multiple sections. For each control I may ask up to 2 follow-up questions — ` +
      `answer as honestly and specifically as you can.`,
      true
    );
    setTimeout(() => loadGapControl(0), 1000);
  } else {
    addBotMessage(
      `Welcome. I'll be your <strong>${escapeHtml(state.framework)}</strong> compliance auditor for ` +
      `<strong>${escapeHtml(state.orgName)}</strong> today. We have <strong>${state.questions.length} controls</strong> ` +
      `to work through. For each one I may ask a few follow-up questions before we move on. ` +
      `Answer as honestly and specifically as you can.`,
      true
    );
    setTimeout(() => {
      addBotMessage("Before we begin — approximately how many employees does your organisation have?");
      enableInput();
    }, 1000);
  }
}

function showSetupError(msg) {
  const el = document.getElementById("setup-error");
  el.textContent   = msg;
  el.style.display = "block";
}

// ── RISK ASSESSMENT FLOW ───────────────────────────────

async function loadControl(index) {
  if (state.finished) return;
  if (index >= state.questions.length) {
    completeAssessment();
    return;
  }

  state.currentIndex   = index;
  state.followUpCount  = 0;
  state.controlHistory = [];
  state.isProcessing   = false;

  updateProgress();
  addControlDivider(index);

  await callAuditor();
}

async function submitAnswer() {
  const input  = document.getElementById("answer-input");
  const answer = input.value.trim();
  if (!answer || state.isProcessing) return;

  if (answer === "Skip to End") {
    input.value = "";
    skipToEnd();
    return;
  }

  disableInput();
  input.value = "";
  addUserMessage(answer);

  if (state.phase === "employee_count") {
    state.employeeCount = answer;
    state.phase         = "assessment";
    addBotMessage(`Got it — ${escapeHtml(answer)}. Let's begin the assessment.`);
    setTimeout(() => loadControl(0), 1000);
    return;
  }

  state.isProcessing   = true;
  state.controlHistory = [...state.controlHistory, { role: "user", content: answer }];

  if (state.mode === "gap") {
    await callGapAuditor();
  } else {
    await callAuditor();
  }
}

async function callAuditor() {
  const control    = state.questions[state.currentIndex];
  const isOpening  = state.controlHistory.length === 0;
  const thinkingId = addThinking();

  try {
    const res = await fetch("/api/chat", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        framework:       state.framework,
        control:         control,
        history:         state.controlHistory,
        follow_up_count: state.followUpCount,
        assignee:        state.assignee,
        employee_count:  state.employeeCount
      })
    });

    const data = await res.json();
    removeThinking(thinkingId);
    if (state.finished) return;   // user skipped to the end while Claude was thinking

    if (!data.success) {
      addBotMessage("I encountered an error. Please try again.");
      enableInput();
      state.isProcessing = false;
      return;
    }

    const { result, history } = data;
    state.controlHistory = history;

    if (result.action === "followup") {
      if (!isOpening) state.followUpCount++;
      addBotMessage(result.message);
      enableInput();
      state.isProcessing = false;
    } else if (result.action === "assess") {
      disableInput();
      addAssessmentCard(result.message, result.data, state.currentIndex);
      state.results.push(result.data);
      updateProgress();
      setTimeout(() => loadControl(state.currentIndex + 1), 3500);
    }

  } catch {
    removeThinking(thinkingId);
    if (state.finished) return;
    addBotMessage("Connection error. Please try again.");
    enableInput();
    state.isProcessing = false;
  }
}

// ── GAP ASSESSMENT FLOW ────────────────────────────────

async function loadGapControl(index) {
  if (state.finished) return;
  if (index >= state.questions.length) {
    completeGapAssessment();
    return;
  }

  const control        = state.questions[index];
  state.currentIndex   = index;
  state.followUpCount  = 0;
  state.controlHistory = [];
  state.isProcessing   = false;

  // Section banner when section changes
  if (control.section !== state.currentSection) {
    state.currentSection = control.section;
    addSectionBanner(control.section);
  }

  updateProgress();
  addControlDivider(index);

  await callGapAuditor();
}

async function callGapAuditor() {
  const control    = state.questions[state.currentIndex];
  const isOpening  = state.controlHistory.length === 0;
  const thinkingId = addThinking();

  try {
    const res = await fetch("/api/gap-chat", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        framework:       state.framework,
        control:         control,
        history:         state.controlHistory,
        follow_up_count: state.followUpCount,
        assignee:        state.assignee
      })
    });

    const data = await res.json();
    removeThinking(thinkingId);
    if (state.finished) return;   // user skipped to the end while Claude was thinking

    if (!data.success) {
      addBotMessage("I encountered an error. Please try again.");
      enableInput();
      state.isProcessing = false;
      return;
    }

    const { result, history } = data;
    state.controlHistory = history;

    if (result.action === "followup") {
      if (!isOpening) state.followUpCount++;
      addBotMessage(result.message);
      enableInput();
      state.isProcessing = false;
    } else if (result.action === "assess") {
      disableInput();
      addGapAssessmentCard(result.message, result.data, state.currentIndex);
      state.gapResults.push(result.data);
      updateProgress();
      setTimeout(() => loadGapControl(state.currentIndex + 1), 3500);
    }

  } catch {
    removeThinking(thinkingId);
    if (state.finished) return;
    addBotMessage("Connection error. Please try again.");
    enableInput();
    state.isProcessing = false;
  }
}

// ── COMPLETION ─────────────────────────────────────────

// ── SKIP TO END (demo shortcut) ─────────────────────────
// Lets a reviewer jump straight to the report. Controls not yet answered are
// filled with realistic sample findings, each clearly labelled as a sample.

const SAMPLE_NOTE = "Sample finding (assessment skipped).";

// Hand-written sample findings for the shared RSK001–RSK030 control set.
const SAMPLE_RISKS = {
  RSK001: ["Unauthorised logical access to internal networks", "TECHNOLOGY", "Cloudflare Zero Trust", "Put internal services behind a zero-trust access gateway and remove direct VPN-wide access."],
  RSK002: ["Weak access control on production servers", "TECHNOLOGY", "Teleport", "Route production access through a bastion with named accounts and session logging."],
  RSK003: ["Data leakage via external storage devices", "TECHNOLOGY", "Microsoft Intune", "Block USB mass storage by device policy, with an exception process for approved needs."],
  RSK004: ["Unauthorised access to unattended laptops", "PEOPLES", "Microsoft Intune", "Enforce screen lock after 5 minutes and Windows Hello / Touch ID sign-in."],
  RSK005: ["Inconsistent identity and access management", "GOVERNANCE", "Okta", "Centralise sign-in through SSO and document a joiner-mover-leaver access policy."],
  RSK006: ["MFA not enforced on critical network components", "TECHNOLOGY", "Okta Verify", "Turn on MFA for all admin consoles, VPN and cloud accounts, starting with admins."],
  RSK007: ["Company assets not recovered when staff leave", "OPERATIONS", "Snipe-IT", "Add asset return to the offboarding checklist and track devices in an asset register."],
  RSK008: ["Unpatched applications exposing known vulnerabilities", "TECHNOLOGY", "Microsoft Intune", "Enable automatic updates for OS and browsers and review update compliance monthly."],
  RSK009: ["Installation of unauthorised or pirated software", "REGULATORY", "Microsoft Intune", "Restrict local admin rights and publish an approved software list."],
  RSK010: ["Linux servers missing security patches", "TECHNOLOGY", "Ubuntu Landscape", "Enable unattended security upgrades and patch critical CVEs within 14 days."],
  RSK011: ["Known vulnerabilities not tracked to closure", "TECHNOLOGY", "Tenable Nessus", "Run monthly vulnerability scans and track findings to closure with agreed SLAs."],
  RSK012: ["Insecure API configuration enabling data exposure", "TECHNOLOGY", "Cloudflare API Shield", "Require authentication and rate limiting on all public APIs and review them yearly."],
  RSK013: ["Malware infection without effective monitoring", "TECHNOLOGY", "Bitdefender GravityZone", "Deploy managed endpoint protection with central alerting on every device."],
  RSK014: ["Security incidents missed due to limited logging", "OPERATIONS", "Wazuh", "Centralise security logs and set alerts for failed logins and privilege changes."],
  RSK015: ["Sensitive data stored in unencrypted databases", "TECHNOLOGY", "AWS KMS", "Enable encryption at rest on all production databases using managed keys."],
  RSK016: ["Data exposure from lost or stolen laptops", "TECHNOLOGY", "BitLocker / FileVault", "Enforce full disk encryption through device management and report compliance."],
  RSK017: ["Breach of sensitive business information", "CUSTOMER", "Microsoft Purview", "Label sensitive data and restrict sharing of confidential files outside the company."],
  RSK018: ["Data recovered from improperly disposed hardware", "OPERATIONS", "Certified disposal vendor", "Use a certified disposal vendor and keep certificates of destruction."],
  RSK019: ["Insecure transfer of sensitive information", "TECHNOLOGY", "Google Workspace", "Share sensitive files only through managed workspace links, never email attachments."],
  RSK020: ["Data loss during migrations or storage failures", "RESILIENCE", "Veeam", "Take verified backups before migrations and test restores every quarter."],
  RSK021: ["Unauthorised physical access to premises", "OPERATIONS", "Kisi", "Use badge-based door access and keep a visitor log."],
  RSK022: ["Insecure FTP/HTTP services exposed at the firewall", "TECHNOLOGY", "FortiGate", "Disable FTP and plain HTTP at the firewall; allow only SFTP and HTTPS."],
  RSK023: ["Service outage from a primary cloud failure", "RESILIENCE", "AWS Multi-AZ", "Run production across two availability zones and document failover steps."],
  RSK024: ["Downtime from unmonitored network device failure", "RESILIENCE", "PRTG Network Monitor", "Monitor network devices and keep configuration backups for quick replacement."],
  RSK025: ["Operations halted by ISP disruption", "VENDOR MANAGEMENT", "Secondary ISP", "Add a backup internet connection or 5G failover for the office."],
  RSK026: ["Staff unaware of security policies", "PEOPLES", "KnowBe4", "Run annual security awareness training with quarterly phishing simulations."],
  RSK027: ["Customer access lost under high resource load", "CUSTOMER", "AWS Auto Scaling", "Set autoscaling and alerts on CPU and memory for production services."],
  RSK028: ["No business continuity plan for major disruptions", "RESILIENCE", "Business continuity plan", "Write a one-page continuity plan with roles and contacts, and test it yearly."],
  RSK029: ["Dependence on a single cloud security provider", "VENDOR MANAGEMENT", "Vendor risk register", "Document an exit plan and keep data exportable in standard formats."],
  RSK030: ["Service disruption from denial-of-service attacks", "TECHNOLOGY", "Cloudflare", "Put public services behind a DDoS-protected CDN with rate limiting."]
};

// Fixed rotation so every skipped run gives the same varied mix of statuses.
const SAMPLE_RISK_STATUSES = ["OPEN", "TREATED", "OPEN", "ASSESSED", "TREATED", "OPEN", "CLOSED", "TREATED", "OPEN", "ASSESSED",
                              "OPEN", "TREATED", "CLOSED", "OPEN", "TREATED", "ASSESSED", "OPEN", "TREATED", "CLOSED", "OPEN"];
const SAMPLE_GAP_STATUSES  = ["Partial Compliant", "Compliant", "Non Compliant", "Partial Compliant", "Compliant",
                              "Need Review", "Partial Compliant", "Non Compliant", "Compliant", "Partial Compliant"];

function sampleRiskFinding(control, i) {
  const [name, category, app, treatment] = SAMPLE_RISKS[control.id] || [
    control.question.replace(/\?.*$/, ""), "OPERATIONS", "—", "Review this control with the responsible owner."
  ];
  const status = SAMPLE_RISK_STATUSES[i % SAMPLE_RISK_STATUSES.length];
  // Treated / closed risks sit lower than their inherent score.
  const reduction = { OPEN: 0, ASSESSED: i % 2, TREATED: 1 + (i % 2), CLOSED: 2 }[status];
  const inherentL = control.likelihood || 3;
  const inherentI = control.impact     || 3;

  return {
    name,
    description:              `${SAMPLE_NOTE} ${control.question}`,
    category,
    application_name:         app,
    status,
    residual_risk_likelihood: Math.max(1, inherentL - reduction),
    residual_risk_impact:     Math.max(1, inherentI - (reduction > 1 ? 1 : 0)),
    treatment,
    assignee:                 state.assignee,
    entities:                 "ORGANISATION",
    department:               "",
    source:                   "",
    source_type:              "",
    last_assigned:            "",
    likelihood:               control.likelihood,
    impact:                   control.impact,
    loss_of_cia:              control.loss_of_cia
  };
}

function sampleGapFinding(control, i) {
  const status = SAMPLE_GAP_STATUSES[i % SAMPLE_GAP_STATUSES.length];
  const area   = control.control_area || control.id || `Control ${i + 1}`;
  const nature = { "Compliant": "Observation", "Partial Compliant": "Minor",
                   "Non Compliant": "Major", "Need Review": "Observation" }[status];
  const action = {
    "Compliant":         "No action needed — keep evidence current for the audit.",
    "Partial Compliant": `Formalise and document ${area.toLowerCase()}, and assign an owner.`,
    "Non Compliant":     `Implement ${area.toLowerCase()} and collect evidence before the audit.`,
    "Need Review":       `Confirm current practice for ${area.toLowerCase()} with the control owner.`
  }[status];

  return {
    audit_framework: state.framework === "ISO 27001" ? "ISO/IEC 27001" : state.framework,
    name:            area,
    description:     `${SAMPLE_NOTE} ${control.question}`,
    assignee:        state.assignee,
    nature,
    department:      "",
    status,
    action_items:    action
  };
}

function skipToEnd() {
  if (state.finished || !state.questions.length) return;

  const done      = state.mode === "gap" ? state.gapResults.length : state.results.length;
  const remaining = state.questions.length - done;
  if (remaining <= 0) return;
  if (!confirm(`Skip the remaining ${remaining} control${remaining === 1 ? "" : "s"}? They'll be filled with sample findings so you can preview the report.`)) return;

  state.finished = true;
  document.getElementById("skip-btn").style.display = "none";
  document.querySelectorAll("#messages .thinking").forEach(el => el.remove());

  if (state.phase === "employee_count") {
    state.employeeCount = "unknown";
    state.phase = "assessment";
  }

  for (let i = done; i < state.questions.length; i++) {
    const control = state.questions[i];
    if (state.mode === "gap") state.gapResults.push(sampleGapFinding(control, i));
    else                      state.results.push(sampleRiskFinding(control, i));
  }

  state.isProcessing = false;
  disableInput();
  updateProgress();

  addBotMessage(
    `Skipped ahead — the remaining <strong>${remaining}</strong> control${remaining === 1 ? " was" : "s were"} ` +
    `filled with sample findings so you can preview the report.`,
    true
  );

  if (state.mode === "gap") {
    completeGapAssessment();
  } else {
    completeAssessment();
  }
}

function completeAssessment() {
  const total   = state.results.length;
  const open    = state.results.filter(r => r.status === "OPEN").length;
  const treated = state.results.filter(r => r.status === "TREATED").length;
  const closed  = state.results.filter(r => r.status === "CLOSED").length;
  const avgL    = (state.results.reduce((s, r) => s + (r.residual_risk_likelihood || 0), 0) / total).toFixed(1);
  const avgI    = (state.results.reduce((s, r) => s + (r.residual_risk_impact     || 0), 0) / total).toFixed(1);

  const html = `
    <div class="completion-card">
      <h3>Assessment Complete</h3>
      <p>Here is a summary of your <strong>${escapeHtml(state.framework)}</strong> risk assessment for <strong>${escapeHtml(state.orgName)}</strong>.</p>
      <div class="stat-grid">
        <div class="stat-box"><div class="stat-num">${total}</div><div class="stat-label">Controls Assessed</div></div>
        <div class="stat-box"><div class="stat-num">${open}</div><div class="stat-label">Open Risks</div></div>
        <div class="stat-box"><div class="stat-num">${treated}</div><div class="stat-label">Treated</div></div>
        <div class="stat-box"><div class="stat-num">${closed}</div><div class="stat-label">Closed</div></div>
        <div class="stat-box"><div class="stat-num">${avgL}</div><div class="stat-label">Avg Residual Likelihood</div></div>
        <div class="stat-box"><div class="stat-num">${avgI}</div><div class="stat-label">Avg Residual Impact</div></div>
      </div>
      <p style="margin-top:14px;color:#475569;font-size:13px;">
        Click <strong>Complete Assessment</strong> below to submit your report.
      </p>
    </div>`;

  addBotMessage(html, true);
  document.getElementById("complete-bar").style.display  = "flex";
  document.querySelector(".input-area").style.display    = "none";
  document.getElementById("skip-btn").style.display      = "none";
  updateProgress();
}

function completeGapAssessment() {
  const total      = state.gapResults.length;
  const compliant  = state.gapResults.filter(r => r.status === "Compliant").length;
  const partial    = state.gapResults.filter(r => r.status === "Partial Compliant").length;
  const nonComp    = state.gapResults.filter(r => r.status === "Non Compliant").length;
  const review     = state.gapResults.filter(r => r.status === "Need Review").length;

  const html = `
    <div class="completion-card">
      <h3>Gap Assessment Complete</h3>
      <p>Here is a summary of your <strong>${escapeHtml(state.framework)}</strong> gap assessment for <strong>${escapeHtml(state.orgName)}</strong>.</p>
      <div class="stat-grid">
        <div class="stat-box"><div class="stat-num">${total}</div><div class="stat-label">Controls Assessed</div></div>
        <div class="stat-box"><div class="stat-num">${compliant}</div><div class="stat-label">Compliant</div></div>
        <div class="stat-box"><div class="stat-num">${partial}</div><div class="stat-label">Partial Compliant</div></div>
        <div class="stat-box"><div class="stat-num">${nonComp}</div><div class="stat-label">Non Compliant</div></div>
        <div class="stat-box"><div class="stat-num">${review}</div><div class="stat-label">Need Review</div></div>
      </div>
      <p style="margin-top:14px;color:#475569;font-size:13px;">
        Click <strong>Complete Assessment</strong> below to submit your gap register.
      </p>
    </div>`;

  addBotMessage(html, true);
  document.getElementById("complete-bar").style.display  = "flex";
  document.querySelector(".input-area").style.display    = "none";
  document.getElementById("skip-btn").style.display      = "none";
  updateProgress();
}

async function completeAndSend() {
  const btn = document.getElementById("complete-btn");
  btn.disabled    = true;
  btn.textContent = "Sending…";

  if (state.mode === "gap") {
    try {
      const res  = await fetch("/api/gap-export", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ results: state.gapResults, framework: state.framework, org_name: state.orgName })
      });
      const data = await res.json();

      if (data.success) {
        document.getElementById("chat-screen").style.display      = "none";
        document.getElementById("dashboard-screen").style.display = "flex";
        buildGapCompletion(state.gapResults, state.framework, state.orgName);
      } else {
        btn.disabled    = false;
        btn.textContent = "Complete Assessment";
        addBotMessage("There was a problem sending your report. Please try again.");
      }
    } catch {
      btn.disabled    = false;
      btn.textContent = "Complete Assessment";
      addBotMessage("Connection error. Please try again.");
    }
  } else {
    try {
      const res  = await fetch("/api/export", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ results: state.results, framework: state.framework, org_name: state.orgName })
      });
      const data = await res.json();

      if (data.success) {
        document.getElementById("chat-screen").style.display      = "none";
        document.getElementById("dashboard-screen").style.display = "flex";
        buildDashboard(state.results, state.framework, state.orgName);
      } else {
        btn.disabled    = false;
        btn.textContent = "Complete Assessment";
        addBotMessage("There was a problem sending your report. Please try again.");
      }
    } catch {
      btn.disabled    = false;
      btn.textContent = "Complete Assessment";
      addBotMessage("Connection error. Please try again.");
    }
  }
}

function buildDashboard(results, framework, orgName) {
  document.getElementById("dash-title").textContent     = "Risk Dashboard";
  document.getElementById("dash-framework").textContent = framework;
  document.getElementById("dash-org").textContent       = orgName;
  document.getElementById("dash-subtitle").textContent  =
    `${results.length} controls assessed · ${framework} · ${orgName}`;
  document.getElementById("dash-sent-banner").textContent =
    "Your assessment is complete. A full report has been sent to your advisor.";
  document.querySelector(".dash-table-wrap").style.display = "";

  const total    = results.length;
  const open     = results.filter(r => r.status === "OPEN").length;
  const treated  = results.filter(r => r.status === "TREATED").length;
  const closed   = results.filter(r => r.status === "CLOSED").length;
  const assessed = results.filter(r => r.status === "ASSESSED").length;
  const avgL     = total ? (results.reduce((s, r) => s + (r.residual_risk_likelihood || 0), 0) / total).toFixed(1) : "—";
  const avgI     = total ? (results.reduce((s, r) => s + (r.residual_risk_impact     || 0), 0) / total).toFixed(1) : "—";

  const statsData = [
    { num: total,    label: "Total Risks"    },
    { num: open,     label: "Open"           },
    { num: assessed, label: "Assessed"       },
    { num: treated,  label: "Treated"        },
    { num: avgL,     label: "Avg Likelihood" },
    { num: avgI,     label: "Avg Impact"     },
  ];
  document.getElementById("dash-stats").innerHTML = statsData
    .map(s => `<div class="stat-box"><div class="stat-num">${s.num}</div><div class="stat-label">${s.label}</div></div>`)
    .join("");

  const statusClass = { OPEN: "badge-open", ASSESSED: "badge-assessed", TREATED: "badge-treated", CLOSED: "badge-closed" };
  document.getElementById("dash-tbody").innerHTML = results
    .map((r, i) => `
      <tr>
        <td class="dash-num">${i + 1}</td>
        <td class="dash-name">${escapeHtml(r.name || "—")}</td>
        <td><span class="dash-category">${escapeHtml(r.category || "—")}</span></td>
        <td><span class="badge ${statusClass[r.status] || "badge-open"}">${r.status || "OPEN"}</span></td>
        <td class="dash-risk">L ${r.residual_risk_likelihood || "—"} · I ${r.residual_risk_impact || "—"}</td>
        <td class="dash-tool">${escapeHtml(r.application_name || "—")}</td>
        <td class="dash-treatment">${escapeHtml(r.treatment || "—")}</td>
      </tr>`)
    .join("");
}

function buildGapCompletion(results, framework, orgName) {
  document.getElementById("dash-title").textContent     = "Gap Assessment Complete";
  document.getElementById("dash-framework").textContent = `${framework} Gap`;
  document.getElementById("dash-org").textContent       = orgName;
  document.getElementById("dash-subtitle").textContent  =
    `${results.length} controls assessed · ${framework} Gap Assessment · ${orgName}`;
  document.getElementById("dash-sent-banner").textContent =
    "Your gap assessment is complete. Your gap register has been sent to your advisor.";

  // Hide the risk table — not applicable for gap assessment
  document.querySelector(".dash-table-wrap").style.display = "none";

  const total     = results.length;
  const compliant = results.filter(r => r.status === "Compliant").length;
  const partial   = results.filter(r => r.status === "Partial Compliant").length;
  const nonComp   = results.filter(r => r.status === "Non Compliant").length;
  const review    = results.filter(r => r.status === "Need Review").length;
  const na        = results.filter(r => r.status === "Not Applicable").length;

  document.getElementById("dash-stats").innerHTML = [
    { num: total,     label: "Controls Assessed" },
    { num: compliant, label: "Compliant"         },
    { num: partial,   label: "Partial Compliant" },
    { num: nonComp,   label: "Non Compliant"     },
    { num: review,    label: "Need Review"       },
    { num: na,        label: "Not Applicable"    },
  ].map(s => `<div class="stat-box"><div class="stat-num">${s.num}</div><div class="stat-label">${s.label}</div></div>`)
   .join("");
}

// ── UI HELPERS ─────────────────────────────────────────

function addSectionBanner(section) {
  const msgs = document.getElementById("messages");
  const div  = document.createElement("div");
  div.className = "section-banner";
  div.innerHTML = `<span class="section-banner-text">${escapeHtml(section.toUpperCase())}</span>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function addControlDivider(index) {
  const msgs  = document.getElementById("messages");
  const total = state.questions.length;
  const div   = document.createElement("div");
  div.className = "control-divider";
  div.innerHTML = `<span>Control ${index + 1} of ${total}</span>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function addBotMessage(content, isHtml = false) {
  const msgs = document.getElementById("messages");
  const div  = document.createElement("div");
  div.className = "message bot-message";
  div.innerHTML = `
    <div class="avatar"><span class="bot-dot"></span></div>
    <div class="bubble">${isHtml ? content : escapeHtml(content)}</div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function addUserMessage(text) {
  const msgs = document.getElementById("messages");
  const div  = document.createElement("div");
  div.className = "message user-message";
  div.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function addThinking() {
  const msgs = document.getElementById("messages");
  const div  = document.createElement("div");
  const id   = "thinking-" + Date.now();
  div.id        = id;
  div.className = "message bot-message thinking";
  div.innerHTML = `
    <div class="avatar"><span class="bot-dot"></span></div>
    <div class="bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return id;
}

function removeThinking(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function addAssessmentCard(message, data, index) {
  const statusClass = {
    OPEN:     "badge-open",
    ASSESSED: "badge-assessed",
    TREATED:  "badge-treated",
    CLOSED:   "badge-closed"
  }[data.status] || "badge-open";

  const html = `
    <div class="assess-intro">${escapeHtml(message)}</div>
    <div class="assess-card">
      <div class="assess-header">
        <span class="assess-title">${escapeHtml(data.name)}</span>
        <span class="badge ${statusClass}">${data.status}</span>
      </div>
      <div class="assess-body">
        <div class="assess-row">
          <span class="assess-label">Category</span>
          <span class="assess-value">${escapeHtml(data.category)}</span>
        </div>
        <div class="assess-row">
          <span class="assess-label">Residual Risk</span>
          <span class="assess-value">Likelihood ${data.residual_risk_likelihood}/5 · Impact ${data.residual_risk_impact}/5</span>
        </div>
        <div class="assess-row">
          <span class="assess-label">Tool</span>
          <span class="assess-value">${escapeHtml(data.application_name)}</span>
        </div>
        <div class="assess-row">
          <span class="assess-label">Treatment</span>
          <span class="assess-value">${escapeHtml(data.treatment)}</span>
        </div>
      </div>
    </div>
    <div class="assess-footer">Moving to the next control…</div>`;

  const msgs = document.getElementById("messages");
  const div  = document.createElement("div");
  div.className = "message bot-message";
  div.innerHTML = `<div class="avatar"><span class="bot-dot"></span></div><div class="bubble assess-bubble">${html}</div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function addGapAssessmentCard(message, data, index) {
  const statusBadgeClass = {
    "Compliant":                    "badge-compliant",
    "Non Compliant":                "badge-noncompliant",
    "Partial Compliant":            "badge-partial",
    "Need Review":                  "badge-review",
    "Not Applicable":               "badge-na"
  }[data.status] || "badge-review";

  const natureBadgeClass = {
    "Major":                        "badge-nature-major",
    "Minor":                        "badge-nature-minor",
    "Observation":                  "badge-nature-obs",
    "Opportunity for Improvement":  "badge-nature-ofi"
  }[data.nature] || "badge-nature-obs";

  const html = `
    <div class="assess-intro">${escapeHtml(message)}</div>
    <div class="assess-card">
      <div class="assess-header">
        <span class="assess-title">${escapeHtml(data.name)}</span>
        <span class="badge ${statusBadgeClass}">${escapeHtml(data.status)}</span>
      </div>
      <div class="assess-body">
        <div class="assess-row">
          <span class="assess-label">Nature</span>
          <span class="assess-value"><span class="badge ${natureBadgeClass}">${escapeHtml(data.nature)}</span></span>
        </div>
        <div class="assess-row">
          <span class="assess-label">Description</span>
          <span class="assess-value">${escapeHtml(data.description)}</span>
        </div>
        <div class="assess-row">
          <span class="assess-label">Action Item</span>
          <span class="assess-value">${escapeHtml(data.action_items)}</span>
        </div>
      </div>
    </div>
    <div class="assess-footer">Moving to the next control…</div>`;

  const msgs = document.getElementById("messages");
  const div  = document.createElement("div");
  div.className = "message bot-message";
  div.innerHTML = `<div class="avatar"><span class="bot-dot"></span></div><div class="bubble assess-bubble">${html}</div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function updateProgress() {
  const total = state.questions.length;
  const done  = state.mode === "gap" ? state.gapResults.length : state.results.length;
  const pct   = total > 0 ? Math.round((done / total) * 100) : 0;
  document.getElementById("progress-bar").style.width  = pct + "%";
  document.getElementById("progress-text").textContent = `${done} / ${total}`;
}

function enableInput() {
  const inp = document.getElementById("answer-input");
  const btn = document.getElementById("send-btn");
  inp.disabled = false;
  btn.disabled = false;
  inp.focus();
}

function disableInput() {
  document.getElementById("answer-input").disabled = true;
  document.getElementById("send-btn").disabled     = true;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.getElementById("answer-input").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    submitAnswer();
  }
});

document.getElementById("send-btn").addEventListener("click", submitAnswer);

// ── AUTH MODAL ─────────────────────────────────────────

function openAuthModal(tab = 'login') {
  switchAuthTab(tab);
  document.getElementById("auth-modal-backdrop").style.display = "flex";
  const firstInput = tab === 'login'
    ? document.getElementById("login-email")
    : document.getElementById("reg-email");
  setTimeout(() => firstInput && firstInput.focus(), 50);
}

function closeAuthModal() {
  document.getElementById("auth-modal-backdrop").style.display = "none";
  ["login-email","login-password","reg-email","reg-password","reg-confirm","forgot-email"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });
  ["login-error","reg-error","forgot-error"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = "none";
  });
}

function handleBackdropClick(e) {
  if (e.target === document.getElementById("auth-modal-backdrop")) closeAuthModal();
}

function switchAuthTab(tab) {
  document.getElementById("panel-login").style.display    = tab === 'login'    ? "block" : "none";
  document.getElementById("panel-register").style.display = tab === 'register' ? "block" : "none";
  document.getElementById("panel-forgot").style.display   = tab === 'forgot'   ? "block" : "none";
  // "Forgot password" belongs to Sign In, so keep that tab highlighted.
  document.getElementById("tab-login").classList.toggle("active",    tab === 'login' || tab === 'forgot');
  document.getElementById("tab-register").classList.toggle("active", tab === 'register');

  if (tab === 'forgot') {
    const loginEmail  = document.getElementById("login-email").value.trim();
    const forgotEmail = document.getElementById("forgot-email");
    if (loginEmail && !forgotEmail.value) forgotEmail.value = loginEmail;
    document.getElementById("forgot-error").style.display   = "none";
    if (!forgotCooldownActive()) document.getElementById("forgot-success").style.display = "none";
    setTimeout(() => forgotEmail.focus(), 50);
  }
}

// ── Forgot-password cooldown ──
// After a link is sent, the button is greyed out for 5 minutes. The end time
// is kept in localStorage so closing the modal or refreshing doesn't reset it.
const FORGOT_COOLDOWN_MS  = 5 * 60 * 1000;
const FORGOT_COOLDOWN_KEY = "forgotPwCooldownUntil";
const FORGOT_BTN_DEFAULT  = document.getElementById("forgot-btn-label")?.innerHTML;
let forgotCooldownTimer   = null;

function forgotCooldownActive() {
  return Number(localStorage.getItem(FORGOT_COOLDOWN_KEY) || 0) > Date.now();
}

function renderForgotCooldown() {
  const btn   = document.getElementById("forgot-btn");
  const label = document.getElementById("forgot-btn-label");
  const note  = document.getElementById("forgot-cooldown");
  if (!btn) return;

  const remaining = Number(localStorage.getItem(FORGOT_COOLDOWN_KEY) || 0) - Date.now();
  if (remaining > 0) {
    const mins = Math.floor(remaining / 60000);
    const secs = String(Math.floor((remaining % 60000) / 1000)).padStart(2, "0");
    btn.disabled = true;
    btn.classList.add("is-sent");
    label.textContent  = "Reset Link Sent ✓";
    note.textContent   = `You can try again in ${mins}:${secs}`;
    note.style.display = "block";
  } else {
    clearInterval(forgotCooldownTimer);
    forgotCooldownTimer = null;
    localStorage.removeItem(FORGOT_COOLDOWN_KEY);
    btn.disabled = false;
    btn.classList.remove("is-sent");
    label.innerHTML    = FORGOT_BTN_DEFAULT;
    note.style.display = "none";
  }
}

function startForgotCooldown() {
  localStorage.setItem(FORGOT_COOLDOWN_KEY, String(Date.now() + FORGOT_COOLDOWN_MS));
  renderForgotCooldown();
  clearInterval(forgotCooldownTimer);
  forgotCooldownTimer = setInterval(renderForgotCooldown, 1000);
}

// Resume a cooldown that was started before a page refresh.
if (forgotCooldownActive()) {
  renderForgotCooldown();
  forgotCooldownTimer = setInterval(renderForgotCooldown, 1000);
}

async function submitForgotPassword() {
  if (forgotCooldownActive()) return;

  const email     = document.getElementById("forgot-email").value.trim();
  const btn       = document.getElementById("forgot-btn");
  const successEl = document.getElementById("forgot-success");
  document.getElementById("forgot-error").style.display = "none";
  successEl.style.display = "none";

  if (!email) { showAuthError("forgot-error", "Please enter your email."); return; }

  btn.disabled = true;
  try {
    const res  = await fetch("/api/auth/forgot-password", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ email })
    });
    const data = await res.json();
    if (data.success) {
      successEl.textContent   = data.message;
      successEl.style.display = "block";
      startForgotCooldown();
      return;
    }
    showAuthError("forgot-error", data.error || "Couldn't send the reset email.");
  } catch {
    showAuthError("forgot-error", "Network error — please try again.");
  }
  btn.disabled = false;
}

function showAuthError(panelId, msg) {
  const el = document.getElementById(panelId);
  el.textContent   = msg;
  el.style.display = "block";
}

async function submitLogin() {
  const email = document.getElementById("login-email").value.trim();
  const pw    = document.getElementById("login-password").value;
  document.getElementById("login-error").style.display = "none";

  const res  = await fetch("/api/auth/login", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ email, password: pw })
  });
  const data = await res.json();

  if (data.success) {
    window.USER_EMAIL = data.email;
    renderAuthHeaderBtn();
    closeAuthModal();
    if (state.pendingStart) { state.pendingStart = false; showInstructions(); }
  } else {
    showAuthError("login-error", data.error || "Sign in failed.");
  }
}

async function submitRegister() {
  const email   = document.getElementById("reg-email").value.trim();
  const pw      = document.getElementById("reg-password").value;
  const confirm = document.getElementById("reg-confirm").value;
  document.getElementById("reg-error").style.display = "none";

  const res  = await fetch("/api/auth/register", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ email, password: pw, confirm })
  });
  const data = await res.json();

  if (data.success) {
    window.USER_EMAIL = data.email;
    renderAuthHeaderBtn();
    closeAuthModal();
    if (state.pendingStart) { state.pendingStart = false; showInstructions(); }
  } else {
    showAuthError("reg-error", data.error || "Registration failed.");
  }
}

// Allow Enter key in auth modal inputs
["login-email","login-password"].forEach(id => {
  document.getElementById(id)?.addEventListener("keydown", e => {
    if (e.key === "Enter") submitLogin();
  });
});
["reg-email","reg-password","reg-confirm"].forEach(id => {
  document.getElementById(id)?.addEventListener("keydown", e => {
    if (e.key === "Enter") submitRegister();
  });
});
document.getElementById("forgot-email")?.addEventListener("keydown", e => {
  if (e.key === "Enter") submitForgotPassword();
});

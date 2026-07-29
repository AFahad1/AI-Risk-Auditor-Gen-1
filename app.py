import os
import json
import csv
import io
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import anthropic
import resend
from dotenv import load_dotenv
from questions import QUESTIONS, GAP_QUESTIONS
from auth import auth_bp

load_dotenv(override=True)

QUESTION_LIMIT = None

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.register_blueprint(auth_bp)


def _get_supabase():
    from supabase import create_client
    return create_client(
        os.environ.get("SUPABASE_URL"),
        os.environ.get("SUPABASE_KEY")
    )


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "access_token" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/")
def index():
    user_email = session.get("user_email", None)
    return render_template("index.html", user_email=user_email)


@app.route("/api/questions/<framework>")
def get_questions(framework):
    questions = QUESTIONS.get(framework, [])
    if QUESTION_LIMIT is not None:
        questions = questions[:QUESTION_LIMIT]
    return jsonify(questions)


@app.route("/api/gap-questions/<framework>")
def get_gap_questions(framework):
    return jsonify(GAP_QUESTIONS.get(framework, []))


@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    data            = request.json
    framework       = data["framework"]
    control         = data["control"]       # {id, question, loss_of_cia, likelihood, impact}
    history         = data["history"]       # [{role, content}] — empty on first call per control
    follow_up_count = data["follow_up_count"]
    assignee        = data.get("assignee", "")
    employee_count  = data.get("employee_count", "unknown")

    system = _build_system_prompt(framework, control, follow_up_count, employee_count)

    # On the very first call for a control, prime Claude to open the assessment
    messages = history if history else [
        {"role": "user", "content": "Please begin assessing this control."}
    ]

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system,
            messages=messages
        )

        raw  = response.content[0].text.strip()
        text = raw
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        result = json.loads(text)

        if result["action"] == "assess":
            d = result.setdefault("data", {})
            d["assignee"]      = assignee
            d["entities"]      = "ORGANISATION"
            d["department"]    = ""
            d["source"]        = ""
            d["source_type"]   = ""
            d["last_assigned"] = ""
            d["likelihood"]    = control["likelihood"]
            d["impact"]        = control["impact"]
            d["loss_of_cia"]   = control["loss_of_cia"]

        # Return updated history so the frontend can pass it back next call
        updated_history = messages + [{"role": "assistant", "content": raw}]

        return jsonify({"success": True, "result": result, "history": updated_history})

    except json.JSONDecodeError:
        return jsonify({"success": False, "error": "Could not parse Claude response as JSON"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/export", methods=["POST"])
@login_required
def export():
    data      = request.json
    results   = data["results"]
    framework = data.get("framework", "assessment").replace(" ", "_")
    org_name  = data.get("org_name", "Unknown Organisation")
    filename  = f"{framework}_risk_assessment.csv"

    fieldnames = [
        "name", "description", "category", "assignee", "application_name",
        "status", "entities", "department", "source", "source_type",
        "last_assigned", "likelihood", "impact", "residual_risk_impact",
        "residual_risk_likelihood", "treatment", "loss_of_cia"
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(results)
    csv_string = output.getvalue()

    # Persist to Supabase via REST API — no DB password needed
    try:
        sb = _get_supabase()
        sb.table("assessments").insert({
            "user_id":      session["user_id"],
            "framework":    framework,
            "org_name":     org_name,
            "results_json": json.dumps(results)
        }).execute()
    except Exception as e:
        app.logger.warning(f"DB save failed: {e}")

    # Email CSV to owner — wrapped so a failure never blocks the download
    try:
        resend.api_key = os.environ.get("RESEND_API_KEY")
        resend.Emails.send({
            "from":    "Risk Assessment <onboarding@resend.dev>",
            "to":      [os.environ.get("OWNER_EMAIL", "ahfahad17@gmail.com")],
            "subject": f"New Export: {org_name} ({framework})",
            "html": (
                f"<p><strong>Client:</strong> {session['user_email']}<br>"
                f"<strong>Organisation:</strong> {org_name}<br>"
                f"<strong>Framework:</strong> {framework}<br>"
                f"<strong>Controls assessed:</strong> {len(results)}</p>"
            ),
            "attachments": [{"filename": filename, "content": list(csv_string.encode("utf-8"))}]
        })
    except Exception as e:
        app.logger.warning(f"Email send failed: {e}")

    return jsonify({"success": True, "message": "Assessment complete. Your report has been sent."})


@app.route("/api/gap-chat", methods=["POST"])
@login_required
def gap_chat():
    data            = request.json
    framework       = data["framework"]
    control         = data["control"]   # {id, section, control_area, question}
    history         = data["history"]
    follow_up_count = data["follow_up_count"]
    assignee        = data.get("assignee", "")

    system = _build_gap_system_prompt(framework, control, follow_up_count)

    messages = history if history else [
        {"role": "user", "content": "Please begin assessing this control."}
    ]

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system,
            messages=messages
        )

        raw  = response.content[0].text.strip()
        text = raw
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        result = json.loads(text)

        if result["action"] == "assess":
            audit_framework_label = {
                "ISO 27001": "ISO/IEC 27001",
                "SOC 2":     "SOC 2",
            }.get(framework, framework)

            d = result.setdefault("data", {})
            d["audit_framework"] = audit_framework_label
            d["assignee"]        = assignee
            d["department"]      = ""

        updated_history = messages + [{"role": "assistant", "content": raw}]
        return jsonify({"success": True, "result": result, "history": updated_history})

    except json.JSONDecodeError:
        return jsonify({"success": False, "error": "Could not parse Claude response as JSON"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/gap-export", methods=["POST"])
@login_required
def gap_export():
    data      = request.json
    results   = data["results"]
    framework = data.get("framework", "assessment").replace(" ", "_")
    org_name  = data.get("org_name", "Unknown Organisation")
    filename  = f"{framework}_gap_assessment.csv"

    fieldnames = [
        "audit_framework", "name", "description", "assignee",
        "nature", "department", "status", "action_items"
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(results)
    csv_string = output.getvalue()

    try:
        sb = _get_supabase()
        sb.table("assessments").insert({
            "user_id":      session["user_id"],
            "framework":    framework + "_gap",
            "org_name":     org_name,
            "results_json": json.dumps(results)
        }).execute()
    except Exception as e:
        app.logger.warning(f"DB save failed: {e}")

    try:
        resend.api_key = os.environ.get("RESEND_API_KEY")
        resend.Emails.send({
            "from":    "Gap Assessment <onboarding@resend.dev>",
            "to":      [os.environ.get("OWNER_EMAIL", "ahfahad17@gmail.com")],
            "subject": f"New Gap Assessment: {org_name} ({framework})",
            "html": (
                f"<p><strong>Client:</strong> {session['user_email']}<br>"
                f"<strong>Organisation:</strong> {org_name}<br>"
                f"<strong>Framework:</strong> {framework} Gap Assessment<br>"
                f"<strong>Controls assessed:</strong> {len(results)}</p>"
            ),
            "attachments": [{"filename": filename, "content": list(csv_string.encode("utf-8"))}]
        })
    except Exception as e:
        app.logger.warning(f"Email send failed: {e}")

    return jsonify({"success": True, "message": "Gap assessment complete. Your report has been sent."})


FRAMEWORK_TOOLS = {
    "ISO 27001": (
        "Suggest tools aligned with ISO 27001 Annex A controls. "
        "Examples by domain: access control — Okta, Microsoft Entra ID; endpoint — Microsoft Intune, Zoho MDM, Kaspersky Endpoint Security; "
        "vulnerability management — Qualys, Tenable Nessus; logging/SIEM — Wazuh, Graylog; "
        "encryption — BitLocker, VeraCrypt; policy management — Truzta, ConfidentaI; "
        "network security — Cloudflare WAF, pfSense; antivirus — Bitdefender GravityZone, Kaspersky."
    ),
    "SOC 2": (
        "Suggest tools aligned with SOC 2 Trust Service Criteria. "
        "Examples by criteria: logical access (CC6) — Okta MFA, JumpCloud; monitoring (CC7) — Datadog, AWS CloudWatch, Wazuh; "
        "change management (CC8) — Jira, GitHub; availability (A1) — AWS Auto Scaling, Cloudflare; "
        "endpoint (CC6.8) — Microsoft Intune, Zoho MDM; antivirus — Bitdefender GravityZone, Kaspersky Endpoint Security; "
        "vendor management (CC9) — OneTrust; incident response — PagerDuty."
    ),
    "HIPAA": (
        "Suggest tools aligned with HIPAA Security Rule safeguards. "
        "Examples by safeguard: access control (§164.312a) — Okta, Microsoft Entra ID; audit controls (§164.312b) — Splunk, Wazuh; "
        "encryption (§164.312e) — BitLocker, AWS KMS; device management — Microsoft Intune, Zoho MDM; "
        "backup/DR (§164.308a7) — Veeam, AWS Backup; BAA management — Accountable HQ; "
        "training (§164.308a5) — KnowBe4, Proofpoint Security Awareness."
    ),
}

DEFAULT_TOOLS = (
    "Suggest specific, well-known tools relevant to the control area "
    "(e.g. Cloudflare WAF, Okta MFA, Bitdefender GravityZone, Zoho MDM, Microsoft Intune, Kaspersky Endpoint Security)."
)


def _build_system_prompt(framework, control, follow_up_count, employee_count="unknown"):
    remaining   = 3 - follow_up_count
    must_assess = follow_up_count >= 3
    tool_guidance = FRAMEWORK_TOOLS.get(framework, DEFAULT_TOOLS)

    prompt = f"""You are a senior {framework} compliance auditor conducting a structured risk assessment interview. \
You assess one control at a time through natural conversation — concise, professional, and direct.

Organisation size: {employee_count} employees. Calibrate all tool suggestions and treatment recommendations \
to suit this organisation size — a small startup needs lightweight, low-cost tools whereas a larger company \
can handle more enterprise-grade solutions.

Current control:
  ID:                  {control['id']}
  Control question:    {control['question']}
  CIA components:      {control['loss_of_cia']}
  Inherent likelihood: {control['likelihood']}/5
  Inherent impact:     {control['impact']}/5

Follow-up questions used: {follow_up_count} / 3 maximum.
"""

    if must_assess:
        prompt += "\nYou have used all 3 follow-up questions. You MUST now produce your final assessment.\n"
    else:
        prompt += f"You may ask up to {remaining} more follow-up question(s), or assess immediately if you have enough information.\n"

    prompt += f"""
Auditor rules:
- Ask only one question at a time
- Focus follow-ups on: what specific tool or application is used, how long the control has been in place, any gaps or weaknesses
- Never repeat a question already in the conversation
- If the user says they don't know or are unsure, acknowledge it professionally (e.g. "Understood — that's noted as a gap.") and immediately move to the assessment without asking any further questions
- If the user responds with "Out of Scope" or any clear indication that the control is not applicable to their organisation, immediately produce a final assessment with status "CLOSED". Do not ask any follow-up questions. Set name, description, category, application_name, and treatment all to "N/A", set residual_risk_likelihood and residual_risk_impact to 0, and write a brief acknowledgement message (e.g. "Understood — this control is out of scope for your organisation. Moving on.")
- Treatment suggestions must be low-cost, practical, and minimal — just enough to satisfy the framework's requirement, no more
- Keep treatment wording simple and plain — avoid technical jargon or lengthy explanations
- If the client has the control partially in place, explicitly acknowledge what they already have before recommending what is still needed
- If a control relates to policies or secure code review and the client indicates they lack these, reassure them that Truzta (the compliance assistant platform this tool is part of) can help — Truzta can draft policies and perform secure code reviews on their behalf
- When assessing, write a short natural transition message as a real auditor would (e.g. "Good — I have what I need. Here's my assessment before we move on.")
- Tool suggestions: {tool_guidance}

ALWAYS respond with a single valid JSON object only - no markdown, no text outside the JSON.

To ask a follow-up question:
{{
  "action": "followup",
  "message": "Your concise auditor question"
}}

To deliver a final assessment:
{{
  "action": "assess",
  "message": "Short natural transition - summarise the finding in 1-2 sentences then say you're moving on",
  "data": {{
    "name": "Concise risk name (max 12 words)",
    "description": "2-3 sentences describing the risk in the context of {framework} compliance",
    "category": "ONE of: CUSTOMER, GOVERNANCE, OPERATIONS, PEOPLES, REGULATORY, RESILIENCE, TECHNOLOGY, VENDOR MANAGEMENT, OTHER",
    "application_name": "Specific tool or product that addresses this risk",
    "status": "OPEN | ASSESSED | TREATED | CLOSED",
    "residual_risk_impact": "<integer 1-5>",
    "residual_risk_likelihood": "<integer 1-5>",
    "treatment": "Low-cost, actionable recommendation - one or two sentences"
  }}
}}"""

    return prompt


def _build_gap_system_prompt(framework, control, follow_up_count):
    remaining   = 2 - follow_up_count
    must_assess = follow_up_count >= 2

    prompt = f"""You are a senior {framework} gap analyst conducting a structured gap assessment interview. \
You are friendly and professional, but decisive — you have only 2 follow-up questions per control, so every question must count.

Current control:
  Section:      {control['section']}
  Control Area: {control['control_area']}
  Question:     {control['question']}

Follow-up questions used: {follow_up_count} / 2 maximum.
"""

    if must_assess:
        prompt += "\nYou have used all 2 follow-up questions. You MUST now produce your final gap assessment.\n"
    else:
        prompt += f"You may ask up to {remaining} more follow-up question(s), or assess immediately if you have enough information.\n"

    prompt += """
Gap analyst rules:
- Ask only one question at a time
- Focus follow-ups on: whether the control is formally documented, who owns it, and whether evidence exists
- Never repeat a question already in the conversation
- If the user says they don't know or are unsure, acknowledge it professionally and immediately move to the assessment
- If the user responds with "Out of Scope" or any clear indication the control is not applicable, immediately produce a final assessment with status "Not Applicable", nature "Observation", and a brief acknowledgement message — do not ask follow-up questions
- When assessing, write a short natural transition message (e.g. "Thank you — here is my assessment for this control.")
- Keep action items concise — one line only
- Status guidance:
  * Compliant: control is fully implemented with documented evidence
  * Partial Compliant: control exists but has notable gaps in coverage or documentation
  * Non Compliant: control is entirely absent or fundamentally broken
  * Need Review: insufficient information to determine compliance status
  * Not Applicable: control is not applicable to this organisation
- Nature guidance:
  * Major: control is entirely absent or fundamentally broken; directly violates the framework requirement
  * Minor: control exists but has notable gaps; partially meets the requirement
  * Observation: informational finding; not a direct gap but worth noting
  * Opportunity for Improvement: control is largely compliant; suggestion to strengthen it further

ALWAYS respond with a single valid JSON object only — no markdown, no text outside the JSON.

To ask a follow-up question:
{
  "action": "followup",
  "message": "Your concise question"
}

To deliver a final gap assessment:
{
  "action": "assess",
  "message": "Short natural transition — 1-2 sentences",
  "data": {
    "name": "Short gap name — a few words",
    "description": "1-2 line description of the gap for the client organisation",
    "nature": "Major | Minor | Observation | Opportunity for Improvement",
    "status": "Compliant | Non Compliant | Partial Compliant | Need Review | Not Applicable",
    "action_items": "One-line treatment recommendation"
  }
}"""

    return prompt


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)

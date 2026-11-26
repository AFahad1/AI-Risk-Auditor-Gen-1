import os
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from supabase import create_client, ClientOptions

auth_bp = Blueprint("auth", __name__)


def get_supabase(flow_type=None):
    options = ClientOptions(flow_type=flow_type) if flow_type else None
    return create_client(
        os.environ.get("SUPABASE_URL"),
        os.environ.get("SUPABASE_KEY"),
        options=options
    )


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email   = request.form.get("email", "").strip().lower()
        pw      = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not email or not pw:
            return render_template("register.html", error="Email and password are required.")
        if pw != confirm:
            return render_template("register.html", error="Passwords do not match.")

        try:
            sb  = get_supabase()
            res = sb.auth.sign_up({"email": email, "password": pw})
            if res.user:
                session["access_token"] = res.session.access_token
                session["user_id"]      = str(res.user.id)
                session["user_email"]   = res.user.email
                return redirect(url_for("index"))
            return render_template("register.html", error="Registration failed — please try again.")
        except Exception as e:
            return render_template("register.html", error=str(e))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw    = request.form.get("password", "")

        try:
            sb  = get_supabase()
            res = sb.auth.sign_in_with_password({"email": email, "password": pw})
            session["access_token"] = res.session.access_token
            session["user_id"]      = str(res.user.id)
            session["user_email"]   = res.user.email
            return redirect(url_for("index"))
        except Exception:
            return render_template("login.html", error="Invalid email or password.")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@auth_bp.route("/api/auth/login", methods=["POST"])
def api_login():
    data  = request.json or {}
    email = data.get("email", "").strip().lower()
    pw    = data.get("password", "")
    if not email or not pw:
        return jsonify({"success": False, "error": "Email and password are required."}), 400
    try:
        sb  = get_supabase()
        res = sb.auth.sign_in_with_password({"email": email, "password": pw})
        session["access_token"] = res.session.access_token
        session["user_id"]      = str(res.user.id)
        session["user_email"]   = res.user.email
        return jsonify({"success": True, "email": res.user.email})
    except Exception:
        return jsonify({"success": False, "error": "Invalid email or password."}), 401


@auth_bp.route("/api/auth/register", methods=["POST"])
def api_register():
    data     = request.json or {}
    email    = data.get("email", "").strip().lower()
    pw       = data.get("password", "")
    confirm  = data.get("confirm", "")
    if not email or not pw:
        return jsonify({"success": False, "error": "Email and password are required."}), 400
    if pw != confirm:
        return jsonify({"success": False, "error": "Passwords do not match."}), 400
    try:
        sb  = get_supabase()
        res = sb.auth.sign_up({"email": email, "password": pw})
        if not res.user:
            return jsonify({"success": False, "error": "Registration failed — please try again."}), 400
        session["access_token"] = res.session.access_token
        session["user_id"]      = str(res.user.id)
        session["user_email"]   = res.user.email
        return jsonify({"success": True, "email": res.user.email})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


# ── Password reset ──────────────────────────────────────
# 1. /api/auth/forgot-password asks Supabase to email a recovery link.
# 2. The link opens /reset-password with tokens in the URL fragment.
# 3. That page posts the tokens + new password to /api/auth/reset-password.
# The implicit flow is used because PKCE would need the code verifier to
# survive between requests, and get_supabase() makes a fresh client each time.

@auth_bp.route("/api/auth/forgot-password", methods=["POST"])
def api_forgot_password():
    data  = request.json or {}
    email = data.get("email", "").strip().lower()
    if not email:
        return jsonify({"success": False, "error": "Please enter your email."}), 400

    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    redirect_to = f"{proto}://{request.host}{url_for('auth.reset_password_page')}"
    try:
        sb = get_supabase(flow_type="implicit")
        sb.auth.reset_password_for_email(email, {"redirect_to": redirect_to})
    except Exception as e:
        # Supabase often still sends the email even when this call errors
        # (e.g. the auth client's 5 s timeout fires while SMTP is sending),
        # so log it for debugging but don't alarm the user.
        print(f"[forgot-password] {type(e).__name__}: {e}", flush=True)

    # Same response whether or not the account exists, so emails can't be probed.
    return jsonify({"success": True, "message": "Check your email. If an account exists for that address, we've sent a link to reset your password. It may take a minute to arrive, so check your spam folder too."})


@auth_bp.route("/reset-password")
def reset_password_page():
    return render_template("reset_password.html")


@auth_bp.route("/api/auth/reset-password", methods=["POST"])
def api_reset_password():
    data          = request.json or {}
    access_token  = data.get("access_token", "")
    refresh_token = data.get("refresh_token", "")
    pw            = data.get("password", "")
    confirm       = data.get("confirm", "")

    if not access_token or not refresh_token:
        return jsonify({"success": False, "error": "This reset link is invalid or has expired. Please request a new one."}), 400
    if not pw:
        return jsonify({"success": False, "error": "Please enter a new password."}), 400
    if pw != confirm:
        return jsonify({"success": False, "error": "Passwords do not match."}), 400

    try:
        sb  = get_supabase()
        res = sb.auth.set_session(access_token, refresh_token)
    except Exception:
        return jsonify({"success": False, "error": "This reset link is invalid or has expired. Please request a new one."}), 400

    try:
        sb.auth.update_user({"password": pw})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

    session["access_token"] = res.session.access_token
    session["user_id"]      = str(res.user.id)
    session["user_email"]   = res.user.email
    return jsonify({"success": True, "email": res.user.email})

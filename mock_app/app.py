"""
Mock legacy bank servicing tool - the target surface for the automation agent.

Deliberately styled like an old server-rendered enterprise app: nested tables for
layout, no test IDs, an embedded iframe widget, and no client-side framework.
In-memory data only - this is a stand-in, not a real system.
"""

import time
from functools import wraps

from flask import Flask, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = "dev-only-not-a-real-secret"

# --- in-memory "database" -------------------------------------------------

MEMBERS = {
    "12345": {"name": "Jane Doe", "savings_balance": 4231.00, "sub_accounts": []},
    "23456": {"name": "John Smith", "savings_balance": 1500.50, "sub_accounts": ["CD"]},
    "90001": {"name": "Restricted Member", "savings_balance": 999.00, "restricted": True},
}

ACCOUNT_TYPES = ["CD", "Money Market", "Christmas Club"]

_next_confirmation_number = [1000]


def is_restricted(member_id: str) -> bool:
    return MEMBERS.get(member_id, {}).get("restricted", False)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.args.get("force_timeout") == "1":
            session.clear()
            return redirect(url_for("login", expired="1"))
        if not session.get("user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


# --- auth ------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    return redirect(url_for("search") if session.get("user") else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        session["user"] = request.form.get("username", "").strip() or "operator"
        return redirect(url_for("search"))
    return render_template("login.html", expired=request.args.get("expired") == "1")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --- member search / detail -------------------------------------------------

@app.route("/members/search", methods=["GET"])
@login_required
def search():
    query = request.args.get("query", "").strip()
    not_found = bool(query) and query not in MEMBERS
    if query and not not_found:
        return redirect(url_for("member_detail", member_id=query))
    return render_template("search.html", query=query, not_found=not_found)


@app.route("/members/<member_id>", methods=["GET"])
@login_required
def member_detail(member_id):
    if request.args.get("slow") == "1":
        time.sleep(2)
    member = MEMBERS.get(member_id)
    if member is None:
        return render_template("search.html", query=member_id, not_found=True)
    if is_restricted(member_id):
        return render_template("permission_denied.html", member_id=member_id), 403
    return render_template("member_detail.html", member_id=member_id, member=member)


@app.route("/members/<member_id>/widget", methods=["GET"])
@login_required
def member_widget(member_id):
    member = MEMBERS.get(member_id)
    if member is None:
        return "no such member", 404
    return render_template("widget.html", member_id=member_id, member=member)


# --- open sub-account flow (multi-step form -> confirm) --------------------

@app.route("/members/<member_id>/sub-accounts/new", methods=["GET", "POST"])
@login_required
def sub_account_new(member_id):
    member = MEMBERS.get(member_id)
    if member is None:
        return render_template("search.html", query=member_id, not_found=True)
    if is_restricted(member_id):
        return render_template("permission_denied.html", member_id=member_id), 403

    if request.method == "GET":
        return render_template(
            "sub_account_form.html", member_id=member_id, member=member,
            account_types=ACCOUNT_TYPES, error=None,
        )

    account_type = request.form.get("account_type", "")
    deposit_raw = request.form.get("initial_deposit", "")
    purpose = request.form.get("purpose", "").strip()

    error = None
    try:
        deposit = float(deposit_raw)
        if deposit <= 0:
            error = "Initial deposit must be greater than zero."
    except ValueError:
        deposit = None
        error = "Initial deposit must be a number."
    if not account_type:
        error = "Account type is required."

    if error:
        return render_template(
            "sub_account_form.html", member_id=member_id, member=member,
            account_types=ACCOUNT_TYPES, error=error,
            selected_type=account_type, deposit=deposit_raw, purpose=purpose,
        )

    if account_type in member["sub_accounts"]:
        return render_template(
            "sub_account_duplicate_warning.html", member_id=member_id, member=member,
            account_type=account_type, deposit=deposit, purpose=purpose,
        )

    return render_template(
        "sub_account_confirm.html", member_id=member_id, member=member,
        account_type=account_type, deposit=deposit, purpose=purpose,
    )


@app.route("/members/<member_id>/sub-accounts/confirm", methods=["POST"])
@login_required
def sub_account_confirm(member_id):
    member = MEMBERS.get(member_id)
    if member is None:
        return render_template("search.html", query=member_id, not_found=True)

    account_type = request.form.get("account_type")
    deposit = request.form.get("deposit")
    purpose = request.form.get("purpose", "")

    member["sub_accounts"].append(account_type)
    _next_confirmation_number[0] += 1
    confirmation_number = _next_confirmation_number[0]

    return render_template(
        "sub_account_success.html", member_id=member_id, member=member,
        account_type=account_type, deposit=deposit, purpose=purpose,
        confirmation_number=confirmation_number,
    )


if __name__ == "__main__":
    # use_reloader=False: the reloader spawns a second process that actually
    # holds the port, and Ctrl+C on Windows often only kills the watcher,
    # leaving the real server running invisibly in the background.
    app.run(port=5000, debug=True, use_reloader=False)

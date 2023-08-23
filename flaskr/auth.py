import functools

from flask import Blueprint
from flask import flash
from flask import g
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from flask import url_for
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash

from flaskr.db import get_db

#from flaskr.blog import buy_stock

bp = Blueprint("auth", __name__, url_prefix="/auth")

adm_user=["adm"]
adm_password=["123"]


def login_required(view):
    """View decorator that redirects anonymous users to the login page."""

    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))

        return view(**kwargs)

    return wrapped_view


@bp.before_app_request
def load_logged_in_user():
    """If a user id is stored in the session, load the user object from
    the database into ``g.user``."""
    user_id = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        g.user = (
            get_db().execute("SELECT * FROM user WHERE userid = ?", (user_id,)).fetchone()
        )


@bp.route("/register", methods=("GET", "POST"))
def register():
    """Register a new user.

    Validates that the username is not already taken. Hashes the
    password for security.
    """
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        db = get_db()
        error = None

        if not username:
            error = "Username is required."
        elif not password:
            error = "Password is required."

        if error is None:
            try:
                db.execute(
                    "INSERT INTO user (username, password) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
                )
                db.commit()
            except db.IntegrityError:
                # The username was already taken, which caused the
                # commit to fail. Show a validation error.
                error = f"User {username} is already registered."
            else:
                # Success, go to the login page.
                return redirect(url_for("auth.login"))

        flash(error)

    return render_template("auth/register.html")

@bp.route("/manage",methods=("GET","POST"))
@login_required
def manage():
    db = get_db()
    user_id = session.get('user_id')
    username = db.execute("SELECT username from user where userid = ?", (user_id,)).fetchone()
    alluser = db.execute("SELECT username from user;").fetchall()
    alluser_ls = [item[0] for item in alluser]
    if request.method == "POST":
        error=None
        newusername = request.form["username"]
        newpassword = request.form["password"]
        db = get_db()
        if not newusername and not newpassword:
            redirect(url_for("auth.manage"))
        elif not newusername:
            db.execute(
                "UPDATE user SET password=? WHERE userid=?;",(newpassword,user_id,)
            )
        elif not newpassword:
            if newusername in alluser_ls:
                error="Username already existed!"
            else:
                db.execute(
                    "UPDATE user SET username=? WHERE userid=?;", (newusername,user_id,)
                )
        else:
            if newusername in alluser_ls:
                error="Username already existed!"
            else:
                db.execute(
                    "UPDATE user SET username = ?, password = ? WHERE userid = ?;", (newusername, newpassword, user_id,)
                )
        db.commit()
        flash(error)
    return render_template("auth/manage.html", user = username)

@bp.route("/login", methods=("GET", "POST"))
def login():
    """Log in a registered user by adding the user id to the session."""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        db = get_db()
        error = None
        user = db.execute(
            "SELECT * FROM user WHERE username = ?", (username,)
        ).fetchone()

        if user is None:
            error = "Incorrect username."
        elif not check_password_hash(user["password"], password):
            error = "Incorrect password."

        if error is None:
            # store the user id in a new session and return to the index
            session.clear()
            session["user_id"] = user["userid"]
            return redirect(url_for("blog.dashboard"))

        flash(error)

    return render_template("auth/login.html")

@bp.route("/adm_login", methods=("GET", "POST"))
def adm_login():#check the administrator login info
    """Administrator login"""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        db = get_db()
        error = None
        

        
        if username not in adm_user:
            error = "Incorrect username"
        elif password not in adm_password:
            error = "Incorrect password"

        if error is None:
            # store the user id in a new session and return to the index
            session.clear()
            
            return redirect(url_for("blog.adm_dashboard"))

        flash(error)

    return render_template("auth/adm_login.html")


@bp.route("/logout")
def logout():
    """Clear the current session, including the stored user id."""
    session.clear()
    return redirect(url_for("index"))

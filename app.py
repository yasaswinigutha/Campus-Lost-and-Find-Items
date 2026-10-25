from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from models import db, Item, User
from pathlib import Path
from uuid import uuid4

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash
)
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import or_

from models import db, Item, User


app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "static" / "uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app.config["SECRET_KEY"] = "change-this-to-a-long-random-secret-before-deployment"
app.config["SQLALCHEMY_DATABASE_URI"] = (
    "sqlite:///" + str(BASE_DIR / "campus_lost_found.db")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access that page."


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


with app.app_context():
    db.create_all()


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


@app.errorhandler(413)
def file_too_large(error):
    flash("Image must be smaller than 5 MB.", "error")
    return redirect(url_for("report"))


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("Please complete all required fields.", "error")
            return redirect(url_for("register"))

        if len(username) < 3:
            flash("Username must contain at least 3 characters.", "error")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))

        if User.query.filter(
            or_(
                User.username.ilike(username),
                User.email.ilike(email)
            )
        ).first():
            flash("That username or email is already registered.", "error")
            return redirect(url_for("register"))

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role="student"
        )

        try:
            db.session.add(user)
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception("Registration failed")
            flash("Could not create your account. Please try again.", "error")
            return redirect(url_for("register"))

        login_user(user)
        flash("Your account was created successfully!", "success")
        return redirect(url_for("home"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        username_or_email = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(
            or_(
                User.username.ilike(username_or_email),
                User.email.ilike(username_or_email)
            )
        ).first()

        if user is None or not check_password_hash(
            user.password_hash, password
        ):
            flash("Invalid username/email or password.", "error")
            return redirect(url_for("login"))

        login_user(user)
        flash("Login successful. Welcome to CampusFind!", "success")

        next_page = request.args.get("next", "")
        # Only allow local application paths to avoid external redirects.
        if next_page.startswith("/") and not next_page.startswith("//"):
            return redirect(next_page)

        return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/report", methods=["GET", "POST"])
@login_required
def report():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()
        location = request.form.get("location", "").strip()
        item_type = request.form.get("item_type", "").strip()

        image = request.files.get("image")
        image_filename = None
        image_path = None

        if not all([title, description, category, location]):
            flash("Please complete all required fields.", "error")
            return redirect(url_for("report"))

        if item_type not in ("lost", "found"):
            flash("Please select Lost or Found.", "error")
            return redirect(url_for("report"))

        if image and image.filename:
            original_filename = secure_filename(image.filename)

            if not original_filename or not allowed_file(original_filename):
                flash(
                    "Use a PNG, JPG, JPEG, GIF, or WEBP image.",
                    "error"
                )
                return redirect(url_for("report"))

            extension = original_filename.rsplit(".", 1)[1].lower()
            image_filename = f"{uuid4().hex}.{extension}"
            image_path = UPLOAD_FOLDER / image_filename

            try:
                image.save(str(image_path))
            except OSError:
                app.logger.exception("Image upload failed")
                flash("Unable to save the image. Please try again.", "error")
                return redirect(url_for("report"))

        item = Item(
            title=title,
            description=description,
            category=category,
            location=location,
            item_type=item_type,
            image_filename=image_filename,
            user_id=current_user.id
        )

        try:
            db.session.add(item)
            db.session.commit()
        except Exception:
            db.session.rollback()

            if image_path and image_path.exists():
                image_path.unlink()

            app.logger.exception("Saving item report failed")
            flash("Unable to save the report. Please try again.", "error")
            return redirect(url_for("report"))

        flash("Your item report was saved successfully!", "success")
        return redirect(url_for("items", type=item_type))

    return render_template("report.html")


@app.route("/items")
def items():
    item_type = request.args.get("type", "").strip().lower()
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()

    query = Item.query.order_by(Item.created_at.desc())

    if item_type in ("lost", "found"):
        query = query.filter_by(item_type=item_type)

    if search:
        query = query.filter(
            or_(
                Item.title.ilike(f"%{search}%"),
                Item.description.ilike(f"%{search}%")
            )
        )

    if category:
        query = query.filter_by(category=category)

    all_items = query.all()

    return render_template(
        "items.html",
        items=all_items,
        selected_type=item_type,
        search=search,
        selected_category=category
    )


@app.route("/my-reports")
@login_required
def my_reports():
    my_items = (
        Item.query
        .filter_by(user_id=current_user.id)
        .order_by(Item.created_at.desc())
        .all()
    )

    return render_template(
        "items.html",
        items=my_items,
        selected_type="",
        search="",
        selected_category="",
        page_title="My Reports"
    )

@app.route("/claim/<int:item_id>", methods=["GET", "POST"])
@login_required
def claim_item(item_id):
    item = Item.query.get_or_404(item_id)

    if item.item_type.lower() != "found":
        flash("You can only claim items marked as found.", "error")
        return redirect(url_for("items"))

    if item.status.lower() != "open":
        flash("This item is no longer available for claims.", "error")
        return redirect(url_for("items"))

    if item.user_id == current_user.id:
        flash("You cannot claim an item you reported yourself.", "error")
        return redirect(url_for("items"))

    existing_claim = Claim.query.filter_by(
        item_id=item.id,
        user_id=current_user.id,
        status="pending"
    ).first()

    if existing_claim:
        flash("You already have a pending claim for this item.", "info")
        return redirect(url_for("my_claims"))

    if request.method == "POST":
        message = request.form.get("message", "").strip()

        if len(message) < 10:
            flash("Please explain your claim in at least 10 characters.", "error")
            return render_template("claim.html", item=item)

        if len(message) > 1000:
            flash("Your message must be 1000 characters or fewer.", "error")
            return render_template("claim.html", item=item)

        claim = Claim(
            message=message,
            item_id=item.id,
            user_id=current_user.id,
            status="pending"
        )

        db.session.add(claim)
        db.session.commit()

        flash("Your claim was submitted successfully!", "success")
        return redirect(url_for("my_claims"))

    return render_template("claim.html", item=item)


@app.route("/my-claims")
@login_required
def my_claims():
    claims = Claim.query.filter_by(
        user_id=current_user.id
    ).order_by(Claim.created_at.desc()).all()

    return render_template("my_claims.html", claims=claims)


@app.route("/claims")
@login_required
def manage_claims():
    claims = (
        Claim.query.join(Item)
        .filter(Item.user_id == current_user.id)
        .order_by(Claim.created_at.desc())
        .all()
    )

    return render_template("claims.html", claims=claims)


@app.route("/claims/<int:claim_id>/review", methods=["POST"])
@login_required
def review_claim(claim_id):
    claim = Claim.query.get_or_404(claim_id)
    item = Item.query.get_or_404(claim.item_id)

    if item.user_id != current_user.id:
        flash("You are not authorized to review this claim.", "error")
        return redirect(url_for("index"))

    if claim.status != "pending" or item.status != "open":
        flash("This claim can no longer be reviewed.", "error")
        return redirect(url_for("manage_claims"))

    decision = request.form.get("decision", "").lower()

    if decision == "approve":
        claim.status = "approved"
        item.status = "resolved"

        other_claims = Claim.query.filter(
            Claim.item_id == item.id,
            Claim.id != claim.id,
            Claim.status == "pending"
        ).all()

        for other_claim in other_claims:
            other_claim.status = "rejected"

        db.session.commit()
        flash("Claim approved. The item is now marked as resolved.", "success")

    elif decision == "reject":
        claim.status = "rejected"
        db.session.commit()
        flash("Claim rejected.", "info")

    else:
        flash("Invalid review decision.", "error")

    return redirect(url_for("manage_claims"))


if __name__ == "__main__":
    app.run(port=5001, debug=True)


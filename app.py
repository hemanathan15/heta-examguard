import os, io, csv, json, sqlite3, secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import (Flask, g, render_template, request, redirect, url_for, session, flash, jsonify, abort, Response)
from werkzeug.security import generate_password_hash, check_password_hash
import config
from services import exam_service, camera_monitoring, phone_detection

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL, created_at TEXT);
CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY, user_id INTEGER UNIQUE REFERENCES users(id), student_id TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY, user_id INTEGER UNIQUE REFERENCES users(id));
CREATE TABLE IF NOT EXISTS assessments(id INTEGER PRIMARY KEY, title TEXT, subject TEXT, description TEXT, duration INTEGER, total_questions INTEGER,
 marks_per_question REAL, passing_score REAL, start_time TEXT, end_time TEXT, instructions TEXT, access_code TEXT, camera_monitoring INTEGER, nav_monitoring INTEGER,
 warning_limit INTEGER, auto_submit INTEGER, show_answers INTEGER, phone_terminate INTEGER DEFAULT 0, published INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, assessment_id INTEGER REFERENCES assessments(id), position INTEGER, text TEXT, a TEXT, b TEXT, c TEXT, d TEXT, correct TEXT, explanation TEXT, marks REAL);
CREATE TABLE IF NOT EXISTS exam_sessions(id INTEGER PRIMARY KEY, assessment_id INTEGER REFERENCES assessments(id), user_id INTEGER REFERENCES users(id), started_at TEXT, ended_at TEXT,
 status TEXT DEFAULT 'active', face_status TEXT DEFAULT 'unknown', last_seen TEXT, nav_warnings INTEGER DEFAULT 0, face_warnings INTEGER DEFAULT 0, end_reason TEXT);
CREATE TABLE IF NOT EXISTS student_answers(id INTEGER PRIMARY KEY, session_id INTEGER REFERENCES exam_sessions(id), question_id INTEGER REFERENCES questions(id), selected TEXT, marked INTEGER DEFAULT 0, UNIQUE(session_id, question_id));
CREATE TABLE IF NOT EXISTS monitoring_events(id INTEGER PRIMARY KEY, session_id INTEGER REFERENCES exam_sessions(id), type TEXT, detail TEXT, confidence REAL, created_at TEXT);
CREATE TABLE IF NOT EXISTS results(id INTEGER PRIMARY KEY, session_id INTEGER UNIQUE REFERENCES exam_sessions(id), score REAL, total_marks REAL, correct INTEGER, incorrect INTEGER, unanswered INTEGER, percentage REAL, passed INTEGER, time_taken INTEGER, submitted_at TEXT);
"""

# ---------- db helpers ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(config.DATABASE); g.db.row_factory = sqlite3.Row; g.db.execute("PRAGMA foreign_keys=ON")
    return g.db
@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d: d.close()
def q(sql, a=(), one=False):
    c = get_db().execute(sql, a); return c.fetchone() if one else c.fetchall()
def ex(sql, a=()):
    d = get_db(); c = d.execute(sql, a); d.commit(); return c.lastrowid
def now(): return datetime.now().isoformat(timespec="seconds")

def init_db():
    d = sqlite3.connect(config.DATABASE); d.row_factory = sqlite3.Row; d.executescript(SCHEMA)
    if not d.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        uid = d.execute("INSERT INTO users(email,name,password_hash,role,created_at) VALUES(?,?,?,?,?)",
            (config.ADMIN_EMAIL.lower(), config.ADMIN_NAME, generate_password_hash(config.ADMIN_PASSWORD), "admin", now())).lastrowid
        d.execute("INSERT INTO admins(user_id) VALUES(?)", (uid,))
    exam_service.seed(d); d.commit(); d.close()

# ---------- security ----------
@app.before_request
def csrf_protect():
    if "csrf" not in session: session["csrf"] = secrets.token_hex(16)
    if request.method == "POST":
        t = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not t or not secrets.compare_digest(t, session["csrf"]): abort(400, "Invalid CSRF token")
@app.after_request
def headers(r):
    r.headers["X-Frame-Options"] = "DENY"; r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["Permissions-Policy"] = "camera=(self)"; return r
@app.context_processor
def ctx(): return dict(csrf=session.get("csrf", ""), me=current_user())
def current_user():
    uid = session.get("uid"); return q("SELECT * FROM users WHERE id=?", (uid,), True) if uid else None
def login_required(role):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = current_user()
            if not u or u["role"] != role: return redirect(url_for("admin_login" if role == "admin" else "student_login"))
            return f(*a, **k)
        return w
    return deco
student_only, admin_only = login_required("student"), login_required("admin")

# ---------- public / auth ----------
@app.route("/")
def index(): return render_template("index.html")

@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        ident = request.form["identifier"].strip().lower()
        u = q("""SELECT u.* FROM users u LEFT JOIN students s ON s.user_id=u.id WHERE u.role='student' AND (lower(u.email)=? OR lower(s.student_id)=?)""", (ident, ident), True)
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session.clear(); session["uid"] = u["id"]; return redirect(url_for("student_dashboard"))
        flash("Invalid credentials.", "error")
    return render_template("student_login.html")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        u = q("SELECT * FROM users WHERE role='admin' AND lower(email)=?", (request.form["email"].strip().lower(),), True)
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session.clear(); session["uid"] = u["id"]; return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.", "error")
    return render_template("admin_login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form; name, email, sid, pw = f["name"].strip(), f["email"].strip().lower(), f["student_id"].strip(), f["password"]
        if not (name and email and sid) or len(pw) < 8: flash("All fields are required; password must be at least 8 characters.", "error")
        elif q("SELECT 1 FROM users WHERE lower(email)=?", (email,), True) or q("SELECT 1 FROM students WHERE lower(student_id)=?", (sid.lower(),), True):
            flash("Email or Student ID already registered.", "error")
        else:
            uid = ex("INSERT INTO users(email,name,password_hash,role,created_at) VALUES(?,?,?,?,?)", (email, name, generate_password_hash(pw), "student", now()))
            ex("INSERT INTO students(user_id,student_id) VALUES(?,?)", (uid, sid))
            flash("Registration successful. Please log in.", "ok"); return redirect(url_for("student_login"))
    return render_template("register.html")

@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST": flash("If the account exists, ask your administrator to reset the password (Admin > Students > Reset).", "ok")
    return render_template("forgot.html")

@app.route("/logout")
def logout():
    role = (current_user() or {"role": "student"})["role"]; session.clear()
    return redirect(url_for("index"))

# ---------- student ----------
@app.route("/student/dashboard")
@student_only
def student_dashboard():
    u = current_user(); st = q("SELECT * FROM students WHERE user_id=?", (u["id"],), True)
    exams = q("SELECT a.*, (SELECT COUNT(*) FROM questions WHERE assessment_id=a.id) nq FROM assessments a WHERE published=1 ORDER BY id DESC")
    sess = {s["assessment_id"]: s for s in q("SELECT s.*, r.percentage, r.score, r.total_marks, r.passed FROM exam_sessions s LEFT JOIN results r ON r.session_id=s.id WHERE s.user_id=? ORDER BY s.id", (u["id"],))}
    items = []
    for a in exams:
        s = sess.get(a["id"]); n = now()
        state = "completed" if s and s["status"] != "active" else "in_progress" if s else \
                "upcoming" if a["start_time"] and n < a["start_time"] else "closed" if a["end_time"] and n > a["end_time"] else "available"
        items.append((a, s, state))
    return render_template("student_dashboard.html", st=st, items=items)

@app.route("/exam/<int:aid>")
@student_only
def exam_instructions(aid):
    a = q("SELECT * FROM assessments WHERE id=? AND published=1", (aid,), True) or abort(404)
    s = q("SELECT * FROM exam_sessions WHERE assessment_id=? AND user_id=?", (aid, session["uid"]), True)
    if s and s["status"] == "active": return redirect(url_for("exam", sid=s["id"]))
    if s: return redirect(url_for("result", sid=s["id"]))
    return render_template("exam_instructions.html", a=a, nq=q("SELECT COUNT(*) c FROM questions WHERE assessment_id=?", (aid,), True)["c"])

@app.route("/exam/<int:aid>/start", methods=["POST"])
@student_only
def exam_start(aid):
    a = q("SELECT * FROM assessments WHERE id=? AND published=1", (aid,), True) or abort(404)
    if q("SELECT 1 FROM exam_sessions WHERE assessment_id=? AND user_id=?", (aid, session["uid"]), True):
        return redirect(url_for("exam_instructions", aid=aid))
    n = now()
    if (a["start_time"] and n < a["start_time"]) or (a["end_time"] and n > a["end_time"]): flash("This assessment is not open right now.", "error")
    elif a["access_code"] and request.form.get("code", "") != a["access_code"]: flash("Incorrect access code.", "error")
    elif not q("SELECT 1 FROM questions WHERE assessment_id=?", (aid,), True): flash("This assessment has no questions yet.", "error")
    elif not request.form.get("consent"): flash("You must accept the rules and monitoring notice.", "error")
    else:
        sid = ex("INSERT INTO exam_sessions(assessment_id,user_id,started_at,last_seen) VALUES(?,?,?,?)", (aid, session["uid"], n, n))
        return redirect(url_for("exam", sid=sid))
    return redirect(url_for("exam_instructions", aid=aid))

def my_session(sid):
    s = q("SELECT * FROM exam_sessions WHERE id=?", (sid,), True) or abort(404)
    if s["user_id"] != session.get("uid") and not (current_user() and current_user()["role"] == "admin"): abort(403)
    return s
def remaining(s, a):
    end = datetime.fromisoformat(s["started_at"]) + timedelta(minutes=a["duration"])
    return int((end - datetime.now()).total_seconds())

def finish(sid, status, reason=None):
    s = q("SELECT * FROM exam_sessions WHERE id=?", (sid,), True)
    if s["status"] != "active": return False   # prevents duplicate submissions
    a = q("SELECT * FROM assessments WHERE id=?", (s["assessment_id"],), True)
    qs = q("SELECT * FROM questions WHERE assessment_id=?", (a["id"],)); ans = {r["question_id"]: r["selected"] for r in q("SELECT * FROM student_answers WHERE session_id=?", (sid,))}
    score = total = 0; c = i = u = 0
    for x in qs:
        total += x["marks"]; sel = ans.get(x["id"])
        if not sel: u += 1
        elif sel == x["correct"]: c += 1; score += x["marks"]
        else: i += 1
    pct = round(score / total * 100, 1) if total else 0; t = now()
    taken = min(int((datetime.fromisoformat(t) - datetime.fromisoformat(s["started_at"])).total_seconds()), a["duration"] * 60)
    ex("INSERT INTO results(session_id,score,total_marks,correct,incorrect,unanswered,percentage,passed,time_taken,submitted_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
       (sid, score, total, c, i, u, pct, int(pct >= a["passing_score"]), taken, t))
    ex("UPDATE exam_sessions SET status=?, ended_at=?, end_reason=? WHERE id=?", (status, t, reason, sid))
    ex("INSERT INTO monitoring_events(session_id,type,detail,created_at) VALUES(?,?,?,?)", (sid, "assessment_" + status, reason or "", t))
    return True

@app.route("/exam/s/<int:sid>")
@student_only
def exam(sid):
    s = my_session(sid); a = q("SELECT * FROM assessments WHERE id=?", (s["assessment_id"],), True)
    if s["status"] != "active": return redirect(url_for("result", sid=sid))
    if remaining(s, a) <= 0: finish(sid, "submitted", "Time expired"); return redirect(url_for("result", sid=sid))
    qs = [dict(id=x["id"], text=x["text"], options=[x["a"], x["b"], x["c"], x["d"]]) for x in q("SELECT * FROM questions WHERE assessment_id=? ORDER BY position,id", (a["id"],))]  # no answer key
    saved = {r["question_id"]: dict(sel=r["selected"], marked=r["marked"]) for r in q("SELECT * FROM student_answers WHERE session_id=?", (sid,))}
    boot = dict(sid=sid, questions=qs, saved=saved, remaining=remaining(s, a), camera=bool(a["camera_monitoring"]), nav=bool(a["nav_monitoring"]),
                absence=config.ABSENCE_SECONDS, phoneConf=config.PHONE_CONFIDENCE)
    return render_template("exam.html", a=a, boot=boot)

@app.route("/api/session/<int:sid>/answer", methods=["POST"])
@student_only
def api_answer(sid):
    s = my_session(sid); a = q("SELECT * FROM assessments WHERE id=?", (s["assessment_id"],), True)
    if s["status"] != "active": return jsonify(ok=False, redirect=url_for("result", sid=sid))
    if remaining(s, a) < -5: finish(sid, "submitted", "Time expired"); return jsonify(ok=False, redirect=url_for("result", sid=sid))
    d = request.get_json(force=True); qid = int(d["question_id"]); sel = d.get("selected")
    if sel not in (None, "a", "b", "c", "d") or not q("SELECT 1 FROM questions WHERE id=? AND assessment_id=?", (qid, a["id"]), True): abort(400)
    ex("""INSERT INTO student_answers(session_id,question_id,selected,marked) VALUES(?,?,?,?)
          ON CONFLICT(session_id,question_id) DO UPDATE SET selected=excluded.selected, marked=excluded.marked""", (sid, qid, sel, int(bool(d.get("marked")))))
    return jsonify(ok=True)

@app.route("/api/session/<int:sid>/submit", methods=["POST"])
@student_only
def api_submit(sid):
    s = my_session(sid); reason = "Time expired" if (request.get_json(silent=True) or {}).get("auto") else "Submitted by student"
    finish(sid, "submitted", reason); return jsonify(ok=True, redirect=url_for("result", sid=sid))

@app.route("/api/session/<int:sid>/event", methods=["POST"])
@student_only
def api_event(sid):
    s = my_session(sid)
    if s["status"] != "active": return jsonify(terminated=True, redirect=url_for("result", sid=sid))
    a = q("SELECT * FROM assessments WHERE id=?", (s["assessment_id"],), True)
    d = request.get_json(force=True); typ = str(d.get("type", ""))[:40]; conf = d.get("confidence")
    ex("UPDATE exam_sessions SET last_seen=?, face_status=COALESCE(?, face_status) WHERE id=?", (now(), d.get("face_status"), sid))
    if remaining(s, a) < -5 and a["auto_submit"]: finish(sid, "submitted", "Time expired"); return jsonify(terminated=True, redirect=url_for("result", sid=sid))
    if typ == "heartbeat": return jsonify(ok=True, remaining=remaining(s, a))
    allowed = {"face_absence", "multiple_faces", "phone", "tab_hidden", "fullscreen_exit", "window_blur", "camera_lost"}
    if typ not in allowed: abort(400)
    ex("INSERT INTO monitoring_events(session_id,type,detail,confidence,created_at) VALUES(?,?,?,?,?)", (sid, typ, str(d.get("detail", ""))[:200], conf, now()))
    if typ == "phone": msg, term = phone_detection.evaluate(a, float(conf or 0)); col = None
    else: msg, term, col, n = camera_monitoring.evaluate(typ, s, a)
    if col: ex(f"UPDATE exam_sessions SET {col}=? WHERE id=?", (n, sid))
    if term: finish(sid, "terminated", term); return jsonify(terminated=True, redirect=url_for("terminated", sid=sid))
    return jsonify(ok=True, message=msg)

@app.route("/result/<int:sid>")
@login_required("student")
def result(sid):
    s = my_session(sid)
    if s["status"] == "active": return redirect(url_for("exam", sid=sid))
    if s["status"] == "terminated": return redirect(url_for("terminated", sid=sid))
    a = q("SELECT * FROM assessments WHERE id=?", (s["assessment_id"],), True); r = q("SELECT * FROM results WHERE session_id=?", (sid,), True)
    st = q("SELECT * FROM students WHERE user_id=?", (s["user_id"],), True)
    return render_template("results.html", s=s, a=a, r=r, st=st)

@app.route("/terminated/<int:sid>")
@login_required("student")
def terminated(sid):
    s = my_session(sid); a = q("SELECT * FROM assessments WHERE id=?", (s["assessment_id"],), True); st = q("SELECT * FROM students WHERE user_id=?", (s["user_id"],), True)
    return render_template("terminated.html", s=s, a=a, st=st)

@app.route("/review/<int:sid>")
@login_required("student")
def review(sid):
    s = my_session(sid); a = q("SELECT * FROM assessments WHERE id=?", (s["assessment_id"],), True)
    if s["status"] == "active" or not a["show_answers"]: abort(403)
    rows = q("""SELECT qu.*, sa.selected FROM questions qu LEFT JOIN student_answers sa ON sa.question_id=qu.id AND sa.session_id=? WHERE qu.assessment_id=? ORDER BY qu.position,qu.id""", (sid, a["id"]))
    return render_template("answer_review.html", s=s, a=a, rows=rows)

# ---------- admin ----------
@app.route("/admin")
@admin_only
def admin_dashboard():
    c = lambda sql: q(sql, one=True)[0]
    cards = [("Total students", c("SELECT COUNT(*) FROM students")), ("Total assessments", c("SELECT COUNT(*) FROM assessments")), ("Published exams", c("SELECT COUNT(*) FROM assessments WHERE published=1")),
             ("Active sessions", c("SELECT COUNT(*) FROM exam_sessions WHERE status='active'")), ("Completed sessions", c("SELECT COUNT(*) FROM exam_sessions WHERE status='submitted'")),
             ("Terminated sessions", c("SELECT COUNT(*) FROM exam_sessions WHERE status='terminated'")),
             ("Suspicious events", c("SELECT COUNT(*) FROM monitoring_events WHERE type NOT LIKE 'assessment_%'"))]
    part = q("SELECT a.title t, COUNT(s.id) n FROM assessments a LEFT JOIN exam_sessions s ON s.assessment_id=a.id GROUP BY a.id")
    avg = q("SELECT a.title t, ROUND(AVG(r.percentage),1) n FROM assessments a JOIN exam_sessions s ON s.assessment_id=a.id JOIN results r ON r.session_id=s.id GROUP BY a.id")
    pf = q("SELECT SUM(passed) p, SUM(1-passed) f FROM results", one=True)
    mo = q("SELECT substr(started_at,1,7) m, COUNT(*) n FROM exam_sessions GROUP BY m ORDER BY m")
    ch = dict(part=[[r["t"] for r in part], [r["n"] for r in part]], avg=[[r["t"] for r in avg], [r["n"] for r in avg]], pf=[pf["p"] or 0, pf["f"] or 0], mo=[[r["m"] for r in mo], [r["n"] for r in mo]])
    return render_template("admin_dashboard.html", cards=cards, ch=ch, active="dashboard")

@app.route("/admin/students")
@admin_only
def admin_students():
    rows = q("""SELECT u.id, u.name, u.email, s.student_id, (SELECT COUNT(*) FROM exam_sessions WHERE user_id=u.id) n FROM users u JOIN students s ON s.user_id=u.id ORDER BY u.id DESC""")
    return render_template("admin_students.html", rows=rows, active="students")

@app.route("/admin/students/<int:uid>/reset", methods=["POST"])
@admin_only
def admin_reset(uid):
    tmp = secrets.token_urlsafe(8); ex("UPDATE users SET password_hash=? WHERE id=? AND role='student'", (generate_password_hash(tmp), uid))
    flash(f"Temporary password (share securely, shown once): {tmp}", "ok"); return redirect(url_for("admin_students"))

@app.route("/admin/assessments")
@admin_only
def assessment_manager():
    rows = q("SELECT a.*, (SELECT COUNT(*) FROM questions WHERE assessment_id=a.id) nq FROM assessments a ORDER BY id DESC")
    return render_template("assessment_manager.html", rows=rows, active="assessments")

FIELDS = ["title", "subject", "description", "duration", "total_questions", "marks_per_question", "passing_score", "start_time", "end_time", "instructions", "access_code", "warning_limit"]
FLAGS = ["camera_monitoring", "nav_monitoring", "auto_submit", "show_answers", "phone_terminate"]
@app.route("/admin/assessments/new", methods=["GET", "POST"])
@app.route("/admin/assessments/<int:aid>/edit", methods=["GET", "POST"])
@admin_only
def assessment_form(aid=None):
    a = q("SELECT * FROM assessments WHERE id=?", (aid,), True) if aid else None
    if request.method == "POST":
        f = request.form
        try:
            vals = [f["title"].strip(), f["subject"].strip(), f["description"].strip(), max(1, int(f["duration"])), int(f["total_questions"] or 0), float(f["marks_per_question"]), float(f["passing_score"]),
                    f["start_time"], f["end_time"], f["instructions"], f["access_code"].strip(), max(0, int(f["warning_limit"]))] + [int(k in f) for k in FLAGS]
            assert vals[0]
        except (ValueError, KeyError, AssertionError): flash("Please check the form values.", "error"); return render_template("assessment_form.html", a=f, aid=aid, active="assessments")
        if aid: ex("UPDATE assessments SET " + ",".join(k + "=?" for k in FIELDS + FLAGS) + " WHERE id=?", vals + [aid])
        else: aid = ex("INSERT INTO assessments(" + ",".join(FIELDS + FLAGS) + ",created_at) VALUES(" + ",".join("?" * (len(FIELDS + FLAGS) + 1)) + ")", vals + [now()])
        flash("Assessment saved. Now add questions.", "ok"); return redirect(url_for("question_editor", aid=aid))
    return render_template("assessment_form.html", a=a, aid=aid, active="assessments")

@app.route("/admin/assessments/<int:aid>/<action>", methods=["POST"])
@admin_only
def assessment_action(aid, action):
    if action in ("publish", "unpublish"):
        if action == "publish" and not q("SELECT 1 FROM questions WHERE assessment_id=?", (aid,), True): flash("Add at least one question before publishing.", "error")
        else: ex("UPDATE assessments SET published=? WHERE id=?", (int(action == "publish"), aid)); flash("Updated.", "ok")
    elif action == "delete":
        sids = "SELECT id FROM exam_sessions WHERE assessment_id=?"
        for t in ("results", "student_answers", "monitoring_events"): ex(f"DELETE FROM {t} WHERE session_id IN ({sids})", (aid,))
        ex("DELETE FROM exam_sessions WHERE assessment_id=?", (aid,)); ex("DELETE FROM questions WHERE assessment_id=?", (aid,)); ex("DELETE FROM assessments WHERE id=?", (aid,)); flash("Assessment deleted.", "ok")
    return redirect(url_for("assessment_manager"))

@app.route("/admin/assessments/<int:aid>/questions", methods=["GET", "POST"])
@admin_only
def question_editor(aid):
    a = q("SELECT * FROM assessments WHERE id=?", (aid,), True) or abort(404)
    edit = q("SELECT * FROM questions WHERE id=? AND assessment_id=?", (request.args.get("edit"), aid), True) if request.args.get("edit") else None
    if request.method == "POST":
        f = request.form
        try: marks = float(f.get("marks") or a["marks_per_question"]); assert f["text"].strip() and all(f[k].strip() for k in "abcd") and f["correct"] in "abcd"
        except (ValueError, KeyError, AssertionError): flash("Fill the question, all four options and the correct answer.", "error"); return redirect(request.url)
        v = [f["text"].strip(), f["a"].strip(), f["b"].strip(), f["c"].strip(), f["d"].strip(), f["correct"], f["explanation"].strip(), marks]
        if f.get("qid"): ex("UPDATE questions SET text=?,a=?,b=?,c=?,d=?,correct=?,explanation=?,marks=? WHERE id=? AND assessment_id=?", v + [f["qid"], aid])
        else: ex("INSERT INTO questions(text,a,b,c,d,correct,explanation,marks,assessment_id,position) VALUES(?,?,?,?,?,?,?,?,?,(SELECT COALESCE(MAX(position),0)+1 FROM questions WHERE assessment_id=?))", v + [aid, aid])
        flash("Question saved.", "ok"); return redirect(url_for("question_editor", aid=aid))
    qs = q("SELECT * FROM questions WHERE assessment_id=? ORDER BY position,id", (aid,))
    return render_template("question_editor.html", a=a, qs=qs, edit=edit, active="assessments")

@app.route("/admin/questions/<int:qid>/<action>", methods=["POST"])
@admin_only
def question_action(qid, action):
    x = q("SELECT * FROM questions WHERE id=?", (qid,), True) or abort(404)
    if action == "delete": ex("DELETE FROM student_answers WHERE question_id=?", (qid,)); ex("DELETE FROM questions WHERE id=?", (qid,))
    elif action in ("up", "down"):
        qs = [r["id"] for r in q("SELECT id FROM questions WHERE assessment_id=? ORDER BY position,id", (x["assessment_id"],))]; i = qs.index(qid); j = i - 1 if action == "up" else i + 1
        if 0 <= j < len(qs): qs[i], qs[j] = qs[j], qs[i]
        for p, k in enumerate(qs, 1): ex("UPDATE questions SET position=? WHERE id=?", (p, k))
    return redirect(url_for("question_editor", aid=x["assessment_id"]))

@app.route("/admin/question-bank")
@admin_only
def question_bank():
    rows = q("SELECT qu.*, a.title FROM questions qu JOIN assessments a ON a.id=qu.assessment_id ORDER BY a.id, qu.position")
    return render_template("question_bank.html", rows=rows, active="bank")

@app.route("/admin/monitoring")
@admin_only
def live_monitoring(): return render_template("live_monitoring.html", active="monitoring")

@app.route("/admin/api/live")
@admin_only
def api_live():
    out = []
    for s in q("""SELECT s.*, u.name, st.student_id sid_txt, a.title, a.duration FROM exam_sessions s JOIN users u ON u.id=s.user_id LEFT JOIN students st ON st.user_id=u.id JOIN assessments a ON a.id=s.assessment_id WHERE s.status='active'"""):
        rem = remaining(s, s); seen = (datetime.now() - datetime.fromisoformat(s["last_seen"])).total_seconds()
        out.append(dict(name=s["name"], sid=s["sid_txt"], exam=s["title"], camera="offline" if seen > 20 else "online", face=s["face_status"], remaining=max(rem, 0), warnings=s["nav_warnings"] + s["face_warnings"], status=s["status"],
                        events=q("SELECT COUNT(*) c FROM monitoring_events WHERE session_id=?", (s["id"],), True)["c"]))
    ev = [dict(t=e["created_at"], name=e["name"], type=e["type"], detail=e["detail"], conf=e["confidence"]) for e in q(
        "SELECT e.*, u.name FROM monitoring_events e JOIN exam_sessions s ON s.id=e.session_id JOIN users u ON u.id=s.user_id ORDER BY e.id DESC LIMIT 25")]
    return jsonify(sessions=out, events=ev)

def result_rows():
    f = request.args; sql = """SELECT s.id sid, u.name, st.student_id, a.title, a.id aid, s.status, s.started_at, s.end_reason, r.score, r.total_marks, r.percentage, r.passed, r.time_taken,
      s.nav_warnings+s.face_warnings w FROM exam_sessions s JOIN users u ON u.id=s.user_id LEFT JOIN students st ON st.user_id=u.id JOIN assessments a ON a.id=s.assessment_id LEFT JOIN results r ON r.session_id=s.id WHERE 1=1"""
    p = []
    if f.get("student"): sql += " AND (u.name LIKE ? OR st.student_id LIKE ?)"; p += [f"%{f['student']}%"] * 2
    if f.get("assessment"): sql += " AND a.id=?"; p.append(f["assessment"])
    if f.get("date_from"): sql += " AND substr(s.started_at,1,10)>=?"; p.append(f["date_from"])
    if f.get("date_to"): sql += " AND substr(s.started_at,1,10)<=?"; p.append(f["date_to"])
    return q(sql + " ORDER BY s.id DESC", p)

@app.route("/admin/results")
@admin_only
def admin_results():
    ev = q("""SELECT e.*, u.name, a.title FROM monitoring_events e JOIN exam_sessions s ON s.id=e.session_id JOIN users u ON u.id=s.user_id JOIN assessments a ON a.id=s.assessment_id WHERE e.type NOT LIKE 'assessment_%' ORDER BY e.id DESC LIMIT 100""")
    rows = result_rows(); done = [r for r in rows if r["percentage"] is not None]
    stats = dict(n=len(done), avg=round(sum(r["percentage"] for r in done) / len(done), 1) if done else 0, passed=sum(1 for r in done if r["passed"]))
    return render_template("admin_results.html", rows=rows, ev=ev, stats=stats, assessments=q("SELECT id,title FROM assessments"), active="results")

@app.route("/admin/results.csv")
@admin_only
def results_csv():
    o = io.StringIO(); w = csv.writer(o); w.writerow(["Student", "Student ID", "Assessment", "Status", "Started", "Score", "Total", "Percentage", "Passed", "Seconds", "Warnings", "End reason"])
    for r in result_rows(): w.writerow([r["name"], r["student_id"], r["title"], r["status"], r["started_at"], r["score"], r["total_marks"], r["percentage"], r["passed"], r["time_taken"], r["w"], r["end_reason"]])
    return Response(o.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=examguard_results.csv"})

@app.route("/admin/settings", methods=["GET", "POST"])
@admin_only
def admin_settings():
    u = current_user()
    if request.method == "POST":
        if not check_password_hash(u["password_hash"], request.form["current"]): flash("Current password is wrong.", "error")
        elif len(request.form["new"]) < 8 or request.form["new"] != request.form["confirm"]: flash("New passwords must match and be 8+ characters.", "error")
        else: ex("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(request.form["new"]), u["id"])); flash("Password changed.", "ok")
    cutoff = (datetime.now() - timedelta(days=config.EVENT_RETENTION_DAYS)).isoformat()
    return render_template("admin_settings.html", active="settings", retention=config.EVENT_RETENTION_DAYS)

init_db()
if __name__ == "__main__": app.run(debug=True)

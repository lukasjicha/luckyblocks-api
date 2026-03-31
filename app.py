from flask import Flask, request, jsonify
from flask_cors import CORS
import os, time, re
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lb_scores (
            id SERIAL PRIMARY KEY,
            name VARCHAR(20) NOT NULL,
            score INTEGER NOT NULL,
            level INTEGER DEFAULT 1,
            lines INTEGER DEFAULT 0,
            device_id VARCHAR(64),
            ts BIGINT NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def sanitize_name(name):
    name = re.sub(r"[^\w\s\-]", "", name, flags=re.UNICODE)
    return name.strip()[:20] or "Player"

@app.route("/scores", methods=["GET"])
def get_scores():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT name, score, level, lines, device_id, ts FROM lb_scores ORDER BY score DESC LIMIT 100")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/score", methods=["POST"])
def post_score():
    data = request.get_json(silent=True) or {}
    score = data.get("score", 0)
    name = sanitize_name(str(data.get("name", "Player")))
    level = int(data.get("level", 1))
    lines = int(data.get("lines", 0))
    device_id = str(data.get("device_id", ""))[:64]

    if not isinstance(score, int) or score < 0 or score > 9999999:
        return jsonify({"error": "invalid score"}), 400

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if device_id:
        cur.execute("SELECT id, score FROM lb_scores WHERE device_id = %s", (device_id,))
        existing = cur.fetchone()
        if existing:
            if score > existing["score"]:
                cur.execute(
                    "UPDATE lb_scores SET name=%s, score=%s, level=%s, lines=%s, ts=%s WHERE device_id=%s",
                    (name, score, level, lines, int(time.time()*1000), device_id)
                )
            else:
                cur.execute("UPDATE lb_scores SET name=%s WHERE device_id=%s", (name, device_id))
        else:
            cur.execute(
                "INSERT INTO lb_scores (name, score, level, lines, device_id, ts) VALUES (%s,%s,%s,%s,%s,%s)",
                (name, score, level, lines, device_id, int(time.time()*1000))
            )
    else:
        cur.execute(
            "INSERT INTO lb_scores (name, score, level, lines, ts) VALUES (%s,%s,%s,%s,%s)",
            (name, score, level, lines, int(time.time()*1000))
        )

    conn.commit()

    cur.execute("SELECT COUNT(*)+1 as rank FROM lb_scores WHERE score > %s", (score,))
    rank = cur.fetchone()["rank"]

    cur.close()
    conn.close()
    return jsonify({"ok": True, "rank": rank})

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ok", "game": "LuckyBlocks"})

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "game": "LuckyBlocks"})

with app.app_context():
    try:
        init_db()
    except Exception as e:
        print("DB init error:", e)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

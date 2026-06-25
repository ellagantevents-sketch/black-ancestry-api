from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import os

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip().replace("\n", "").replace("\r", "")


def get_db_connection():
    return psycopg2.connect(DATABASE_URL)


@app.route("/")
def home():
    return jsonify({
        "status": "Black Ancestry Census API Running"
    })


@app.route("/search", methods=["GET"])
def search_people():
    last_name = request.args.get("last_name", "").strip()
    first_name = request.args.get("first_name", "").strip()

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    sql = """
        SELECT *
        FROM mississippi_people
        WHERE 1=1
    """
    params = []

    if last_name:
        sql += " AND last_name ILIKE %s"
        params.append(last_name)

    if first_name:
        sql += " AND first_name ILIKE %s"
        params.append(first_name)

    sql += " ORDER BY last_name, first_name LIMIT 100;"

    cur.execute(sql, params)
    results = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({
        "count": len(results),
        "results": results
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

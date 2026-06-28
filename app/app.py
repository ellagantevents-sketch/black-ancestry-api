from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import os

app = Flask(__name__)
CORS(app)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "").strip(),
        port=os.getenv("DB_PORT", "5432").strip(),
        dbname=os.getenv("DB_NAME", "postgres").strip(),
        user=os.getenv("DB_USER", "").strip(),
        password=os.getenv("DB_PASSWORD", "").strip()
    )

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
        FROM people
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

@app.route("/person/<int:person_id>", methods=["GET"])
def get_person(person_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT * FROM people WHERE id = %s;",
        (person_id,)
    )

    person = cur.fetchone()

    if not person:
        cur.close()
        conn.close()
        return jsonify({"error": "Person not found"}), 404

    cur.execute(
        """
        SELECT *
        FROM family_tree_links
        WHERE person_id = %s;
        """,
        (person_id,)
    )

    family_tree = cur.fetchall()

    cur.close()
    conn.close()

    person["family_trees"] = family_tree

    return jsonify(person)
@app.route("/correction", methods=["POST"])
def submit_correction():
    data = request.get_json()

    person_id = data.get("person_id")
    field_name = data.get("field_name")
    original_value = data.get("original_value")
    corrected_value = data.get("corrected_value")
    correction_reason = data.get("correction_reason")
    submitted_by = data.get("submitted_by")

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        INSERT INTO profile_corrections (
            person_id,
            field_name,
            original_value,
            corrected_value,
            correction_reason,
            submitted_by
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *;
        """,
        (
            person_id,
            field_name,
            original_value,
            corrected_value,
            correction_reason,
            submitted_by
        )
    )

    correction = cur.fetchone()

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "correction": correction
    })
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

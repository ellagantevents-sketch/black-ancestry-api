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
    return jsonify({"status": "Black Ancestry Census API Running"})

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

    return jsonify({"count": len(results), "results": results})
@app.route("/person/<int:person_id>", methods=["GET"])
def get_person(person_id):

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT * FROM people WHERE id = %s;",
        (person_id,)
    )

    person = cur.fetchone()
cur.execute("""
SELECT *
FROM family_tree_links
WHERE person_id = %s;
""", (person_id,))

family_tree = cur.fetchall()
    cur.close()
    conn.close()

    if person:
       person["family_trees"] = family_tree

return jsonify(person)
    else:
        return jsonify({"error": "Person not found"}), 404
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

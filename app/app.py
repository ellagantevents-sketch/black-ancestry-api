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

    sql = "SELECT * FROM people WHERE 1=1"
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

    cur.execute("SELECT * FROM people WHERE id = %s;", (person_id,))
    person = cur.fetchone()

    if not person:
        cur.close()
        conn.close()
        return jsonify({"error": "Person not found"}), 404

    cur.execute("SELECT * FROM family_tree_links WHERE person_id = %s ORDER BY id;", (person_id,))
    family_tree = cur.fetchall()

    cur.close()
    conn.close()

    person["family_trees"] = family_tree

    return jsonify(person)


@app.route("/person/<int:person_id>/update", methods=["POST"])
def update_person(person_id):
    data = request.get_json() or {}

    allowed_fields = [
        "first_name",
        "middle_name",
        "last_name",
        "suffix_name",
        "birth_month",
        "birth_day",
        "birth_year",
        "sex",
        "race",
        "mother_first_name",
        "mother_middle_name",
        "mother_last_name",
        "father_first_name",
        "father_middle_name",
        "father_last_name",
        "birth_city",
        "birth_state",
        "profile_photo",
        "photo_url",
        "primary_photo_url",
        "cover_photo_url",
        "biography",
        "story",
        "ai_summary",
        "profile_status",
        "profile_completed",
        "photo_count",
        "verified"
    ]

    updates = []
    values = []

    for field in allowed_fields:
        if field in data:
            updates.append(f"{field} = %s")
            values.append(data[field])

    if not updates:
        return jsonify({"success": False, "error": "No valid fields provided"}), 400

    values.append(person_id)

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    sql = f"""
        UPDATE people
        SET {", ".join(updates)}, last_updated = NOW()
        WHERE id = %s
        RETURNING *;
    """

    cur.execute(sql, values)
    updated_person = cur.fetchone()

    conn.commit()
    cur.close()
    conn.close()

    if not updated_person:
        return jsonify({"success": False, "error": "Person not found"}), 404

    return jsonify({"success": True, "person": updated_person})


@app.route("/family-tree-link", methods=["POST"])
def create_family_tree_link():
    data = request.get_json() or {}

    person_id = data.get("person_id")
    tree_name = data.get("tree_name")
    tree_person_name = data.get("tree_person_name")
    tree_person_id = data.get("tree_person_id")
    relationship_role = data.get("relationship_role")

    if not person_id or not tree_name:
        return jsonify({"success": False, "error": "person_id and tree_name are required"}), 400

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        INSERT INTO family_tree_links (
            person_id,
            tree_name,
            tree_person_name,
            tree_person_id,
            relationship_role
        )
        VALUES (%s, %s, %s, %s, %s)
        RETURNING *;
        """,
        (
            person_id,
            tree_name,
            tree_person_name,
            tree_person_id,
            relationship_role
        )
    )

    link = cur.fetchone()

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"success": True, "family_tree_link": link})


@app.route("/family-tree-link/<int:link_id>/update", methods=["POST"])
def update_family_tree_link(link_id):
    data = request.get_json() or {}

    allowed_fields = [
        "tree_name",
        "tree_person_name",
        "tree_person_id",
        "relationship_role"
    ]

    updates = []
    values = []

    for field in allowed_fields:
        if field in data:
            updates.append(f"{field} = %s")
            values.append(data[field])

    if not updates:
        return jsonify({"success": False, "error": "No valid fields provided"}), 400

    values.append(link_id)

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    sql = f"""
        UPDATE family_tree_links
        SET {", ".join(updates)}
        WHERE id = %s
        RETURNING *;
    """

    cur.execute(sql, values)
    updated_link = cur.fetchone()

    conn.commit()
    cur.close()
    conn.close()

    if not updated_link:
        return jsonify({"success": False, "error": "Family tree link not found"}), 404

    return jsonify({"success": True, "family_tree_link": updated_link})


@app.route("/family-tree-link/<int:link_id>/delete", methods=["POST", "DELETE"])
def delete_family_tree_link(link_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        DELETE FROM family_tree_links
        WHERE id = %s
        RETURNING *;
        """,
        (link_id,)
    )

    deleted_link = cur.fetchone()

    conn.commit()
    cur.close()
    conn.close()

    if not deleted_link:
        return jsonify({"success": False, "error": "Family tree link not found"}), 404

    return jsonify({"success": True, "deleted_family_tree_link": deleted_link})


@app.route("/correction", methods=["POST"])
def submit_correction():
    data = request.get_json() or {}

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

    return jsonify({"success": True, "correction": correction})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

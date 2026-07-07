from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import os
import re

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

    cur.close()
    conn.close()

    if not person:
        return jsonify({"error": "Person not found"}), 404

    return jsonify(person)


def extract_year(text):
    if not text:
        return None
    match = re.search(r"(17|18|19|20)\d{2}", text)
    return int(match.group(0)) if match else None


def parse_name(raw_name):
    if not raw_name:
        return "", "", "", ""

    raw_name = raw_name.replace("/", " ").strip()
    parts = raw_name.split()

    if not parts:
        return "", "", "", ""

    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""
    middle = " ".join(parts[1:-1]) if len(parts) > 2 else ""
    suffix = ""

    return first, middle, last, suffix


def parse_gedcom_text(text):
    people = {}
    families = {}
    current_id = None
    current_type = None
    current_event = None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split(" ", 2)
        level = parts[0]
        tag = parts[1] if len(parts) > 1 else ""
        value = parts[2] if len(parts) > 2 else ""

        if level == "0":
            current_event = None

            if len(parts) >= 3 and parts[1].startswith("@"):
                current_id = parts[1]
                current_type = parts[2]

                if current_type == "INDI":
                    people[current_id] = {
                        "temp_id": current_id,
                        "raw_name": "",
                        "first_name": "",
                        "middle_name": "",
                        "last_name": "",
                        "suffix_name": "",
                        "birth_date": "",
                        "birth_year": None,
                        "birth_place": "",
                        "death_date": "",
                        "death_year": None,
                        "death_place": ""
                    }

                elif current_type == "FAM":
                    families[current_id] = {
                        "temp_id": current_id,
                        "husband": None,
                        "wife": None,
                        "children": []
                    }

            continue

        if not current_id:
            continue

        if current_type == "INDI" and current_id in people:
            person = people[current_id]

            if level == "1" and tag == "NAME":
                person["raw_name"] = value
                first, middle, last, suffix = parse_name(value)
                person["first_name"] = first
                person["middle_name"] = middle
                person["last_name"] = last
                person["suffix_name"] = suffix

            elif level == "1" and tag == "BIRT":
                current_event = "BIRT"

            elif level == "1" and tag == "DEAT":
                current_event = "DEAT"

            elif level == "2" and tag == "DATE" and current_event == "BIRT":
                person["birth_date"] = value
                person["birth_year"] = extract_year(value)

            elif level == "2" and tag == "PLAC" and current_event == "BIRT":
                person["birth_place"] = value

            elif level == "2" and tag == "DATE" and current_event == "DEAT":
                person["death_date"] = value
                person["death_year"] = extract_year(value)

            elif level == "2" and tag == "PLAC" and current_event == "DEAT":
                person["death_place"] = value

        elif current_type == "FAM" and current_id in families:
            fam = families[current_id]

            if level == "1" and tag == "HUSB":
                fam["husband"] = value

            elif level == "1" and tag == "WIFE":
                fam["wife"] = value

            elif level == "1" and tag == "CHIL":
                fam["children"].append(value)

    relationships = []

    for fam in families.values():
        husband = fam.get("husband")
        wife = fam.get("wife")
        children = fam.get("children", [])

        if husband and wife:
            relationships.append({
                "person_temp_id": husband,
                "related_temp_id": wife,
                "relationship_type": "spouse"
            })
            relationships.append({
                "person_temp_id": wife,
                "related_temp_id": husband,
                "relationship_type": "spouse"
            })

        for child in children:
            if husband:
                relationships.append({
                    "person_temp_id": husband,
                    "related_temp_id": child,
                    "relationship_type": "father"
                })
                relationships.append({
                    "person_temp_id": child,
                    "related_temp_id": husband,
                    "relationship_type": "child"
                })

            if wife:
                relationships.append({
                    "person_temp_id": wife,
                    "related_temp_id": child,
                    "relationship_type": "mother"
                })
                relationships.append({
                    "person_temp_id": child,
                    "related_temp_id": wife,
                    "relationship_type": "child"
                })

    return list(people.values()), relationships


@app.route("/gedcom/preview", methods=["POST"])
def gedcom_preview():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No GEDCOM file uploaded"}), 400

    file = request.files["file"]
    tree_name = request.form.get("tree_name", "Uploaded Family Tree")
    owner_email = request.form.get("owner_email", "")

    content = file.read().decode("utf-8", errors="ignore")
    people, relationships = parse_gedcom_text(content)

    return jsonify({
        "success": True,
        "tree_name": tree_name,
        "owner_email": owner_email,
        "people_count": len(people),
        "relationships_count": len(relationships),
        "people_preview": people[:25],
        "relationships_preview": relationships[:50],
        "people": people,
        "relationships": relationships
    })


@app.route("/gedcom/confirm", methods=["POST"])
def gedcom_confirm():
    data = request.get_json() or {}

    tree_name = data.get("tree_name", "Uploaded Family Tree")
    owner_email = data.get("owner_email", "")
    people = data.get("people", [])
    relationships = data.get("relationships", [])

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        INSERT INTO family_trees (tree_name, owner_email, source)
        VALUES (%s, %s, %s)
        RETURNING id;
        """,
        (tree_name, owner_email, "GEDCOM Upload")
    )

    tree_id = cur.fetchone()["id"]
    temp_to_person_id = {}

    for person in people:
        cur.execute(
            """
            INSERT INTO people (
                first_name,
                middle_name,
                last_name,
                suffix_name,
                birth_year,
                birth_city,
                source
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                person.get("first_name"),
                person.get("middle_name"),
                person.get("last_name"),
                person.get("suffix_name"),
                person.get("birth_year"),
                person.get("birth_place"),
                "GEDCOM Upload"
            )
        )

        new_person_id = cur.fetchone()["id"]
        temp_to_person_id[person.get("temp_id")] = new_person_id

        cur.execute(
            """
            INSERT INTO family_tree_people (
                tree_id,
                person_id,
                gedcom_temp_id
            )
            VALUES (%s, %s, %s);
            """,
            (
                tree_id,
                new_person_id,
                person.get("temp_id")
            )
        )

    imported_relationships = 0

    for rel in relationships:
        person_id = temp_to_person_id.get(rel.get("person_temp_id"))
        related_person_id = temp_to_person_id.get(rel.get("related_temp_id"))

        if not person_id or not related_person_id:
            continue

        cur.execute(
            """
            INSERT INTO family_relationships (
                tree_id,
                person_id,
                related_person_id,
                relationship_type
            )
            VALUES (%s, %s, %s, %s);
            """,
            (
                tree_id,
                person_id,
                related_person_id,
                rel.get("relationship_type")
            )
        )

        imported_relationships += 1

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "tree_id": tree_id,
        "people_imported": len(temp_to_person_id),
        "relationships_imported": imported_relationships
    })


@app.route("/family-tree/<int:tree_id>", methods=["GET"])
def get_family_tree(tree_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        SELECT *
        FROM family_trees
        WHERE id = %s;
        """,
        (tree_id,)
    )

    tree = cur.fetchone()

    if not tree:
        cur.close()
        conn.close()
        return jsonify({"success": False, "error": "Tree not found"}), 404

    cur.execute(
        """
        SELECT
            p.*,
            ftp.gedcom_temp_id
        FROM family_tree_people ftp
        JOIN people p ON p.id = ftp.person_id
        WHERE ftp.tree_id = %s
        ORDER BY p.last_name, p.first_name;
        """,
        (tree_id,)
    )

    people = cur.fetchall()

    cur.execute(
        """
        SELECT
            fr.id,
            fr.tree_id,
            fr.person_id,
            fr.related_person_id,
            fr.relationship_type,

            p1.first_name AS person_first_name,
            p1.middle_name AS person_middle_name,
            p1.last_name AS person_last_name,

            p2.first_name AS related_first_name,
            p2.middle_name AS related_middle_name,
            p2.last_name AS related_last_name

        FROM family_relationships fr
        JOIN people p1 ON p1.id = fr.person_id
        JOIN people p2 ON p2.id = fr.related_person_id
        WHERE fr.tree_id = %s
        ORDER BY fr.relationship_type;
        """,
        (tree_id,)
    )

    relationships = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "tree": tree,
        "people_count": len(people),
        "relationships_count": len(relationships),
        "people": people,
        "relationships": relationships
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import os
import requests

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


@app.route("/import-jobs", methods=["GET"])
def get_import_jobs():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT *
        FROM import_jobs
        ORDER BY county;
    """)

    jobs = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify({"count": len(jobs), "jobs": jobs})


def import_one_ms_1950_county(county_requested):
    url = "https://nara-1950-census.s3.us-east-2.amazonaws.com/metadata/json/ms.json"
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    data = response.json()

    state = data.get("state", "Mississippi")
    state_abbreviation = data.get("abbreviation", "MS")
    counties = data.get("county/city", [])

    matched_county = None
    for county_item in counties:
        if county_item.get("name", "").lower() == county_requested.lower():
            matched_county = county_item
            break

    if not matched_county:
        return jsonify({"success": False, "error": f"County not found: {county_requested}"}), 404

    county_name = matched_county.get("name")
    inserted = 0
    skipped = 0

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE import_jobs
            SET status = 'running',
                started_at = NOW(),
                updated_at = NOW(),
                error_message = NULL
            WHERE census_year = 1950
              AND state_abbreviation = 'MS'
              AND county = %s;
        """, (county_name,))

        for enum in matched_county.get("enumeration", []):
            ed = enum.get("ed")
            description = enum.get("description")
            roll = enum.get("roll")

            schedule_image = enum.get("schedule_image") or {}
            folder = schedule_image.get("folder")
            files = schedule_image.get("files") or []

            for image_file in files:
                if not folder or not image_file:
                    skipped += 1
                    continue

                image_url = f"https://nara-1950-census.s3.us-east-2.amazonaws.com/{folder}/{image_file}"

                cur.execute(
                    "SELECT id FROM census_images WHERE image_url = %s LIMIT 1;",
                    (image_url,)
                )

                if cur.fetchone():
                    skipped += 1
                    continue

                cur.execute("""
                    INSERT INTO census_images (
                        census_year,
                        state,
                        state_abbreviation,
                        county,
                        enumeration_district,
                        description,
                        roll,
                        folder,
                        image_file,
                        image_url,
                        source
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    1950,
                    state,
                    state_abbreviation,
                    county_name,
                    ed,
                    description,
                    roll,
                    folder,
                    image_file,
                    image_url,
                    "NARA 1950 Census AWS"
                ))

                inserted += 1

        cur.execute("""
            UPDATE import_jobs
            SET status = 'complete',
                inserted_count = inserted_count + %s,
                skipped_count = skipped_count + %s,
                completed_at = NOW(),
                updated_at = NOW()
            WHERE census_year = 1950
              AND state_abbreviation = 'MS'
              AND county = %s;
        """, (inserted, skipped, county_name))

        conn.commit()

    except Exception as e:
        conn.rollback()

        cur.execute("""
            UPDATE import_jobs
            SET status = 'error',
                error_message = %s,
                updated_at = NOW()
            WHERE census_year = 1950
              AND state_abbreviation = 'MS'
              AND county = %s;
        """, (str(e), county_name))

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "success": False,
            "county": county_name,
            "error": str(e)
        }), 500

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "county": county_name,
        "inserted": inserted,
        "skipped": skipped
    })


@app.route("/import-census-images/ms-1950", methods=["GET"])
def import_ms_1950_census_images_by_county():
    county_requested = request.args.get("county", "").strip()

    if not county_requested:
        return jsonify({
            "message": "Add ?county=CountyName to import one county at a time.",
            "example": "/import-census-images/ms-1950?county=Adams"
        })

    return import_one_ms_1950_county(county_requested)


@app.route("/harvest/ms-1950/remaining", methods=["GET"])
def harvest_remaining_ms_1950():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT county
        FROM import_jobs
        WHERE census_year = 1950
          AND state_abbreviation = 'MS'
          AND status <> 'complete'
        ORDER BY county
        LIMIT 1;
    """)

    job = cur.fetchone()
    cur.close()
    conn.close()

    if not job:
        return jsonify({
            "success": True,
            "message": "All Mississippi counties are complete."
        })

    return import_one_ms_1950_county(job["county"])


@app.route("/census-images/search", methods=["GET"])
def search_census_images():
    county = request.args.get("county", "").strip()
    ed = request.args.get("ed", "").strip()

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    sql = """
        SELECT *
        FROM census_images
        WHERE census_year = 1950
        AND state_abbreviation = 'MS'
    """
    params = []

    if county:
        sql += " AND county ILIKE %s"
        params.append(county)

    if ed:
        sql += " AND enumeration_district ILIKE %s"
        params.append(ed)

    sql += " ORDER BY county, enumeration_district, image_file LIMIT 100;"

    cur.execute(sql, params)
    results = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({"count": len(results), "results": results})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

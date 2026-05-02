#!/usr/bin/env python3
"""
CBT Mock AI — Database Setup Script
Run this once after cloning the project to create the database and tables.

Usage:
    python setup_db.py           # Create DB + tables
    python setup_db.py --reset   # Drop all tables and recreate (DESTRUCTIVE)
    python setup_db.py --seed    # Create DB + tables + sample data for testing
"""

import sys
import os

# Load .env before anything else
from dotenv import load_dotenv
load_dotenv()

from config import Config


def get_connection_parts():
    """Parse the DATABASE_URL into psycopg2-usable parts."""
    from urllib.parse import urlparse
    url = urlparse(Config.SQLALCHEMY_DATABASE_URI)
    return {
        'host':     url.hostname or 'localhost',
        'port':     url.port or 5432,
        'user':     url.username or 'postgres',
        'password': url.password or 'postgres',
        'dbname':   url.path.lstrip('/'),
    }


def create_database_if_not_exists():
    """Connect to the 'postgres' maintenance DB and create the app DB if missing."""
    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    except ImportError:
        print("ERROR: psycopg2-binary is not installed.")
        print("       Run: pip install psycopg2-binary")
        sys.exit(1)

    parts = get_connection_parts()
    target_db = parts['dbname']

    print(f"Connecting to PostgreSQL at {parts['host']}:{parts['port']} as '{parts['user']}'...")

    try:
        # Connect to the default 'postgres' database to check/create our database
        conn = psycopg2.connect(
            host=parts['host'],
            port=parts['port'],
            user=parts['user'],
            password=parts['password'],
            dbname='postgres',
            connect_timeout=5,
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()

        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
        exists = cur.fetchone()

        if not exists:
            cur.execute(f'CREATE DATABASE "{target_db}"')
            print(f"  Created database: {target_db}")
        else:
            print(f"  Database '{target_db}' already exists.")

        cur.close()
        conn.close()
        return True

    except psycopg2.OperationalError as e:
        print(f"\nERROR: Could not connect to PostgreSQL.\n  {e}")
        print("\nTroubleshooting:")
        print("  1. Make sure PostgreSQL is running:")
        print("       macOS:   brew services start postgresql")
        print("       Ubuntu:  sudo service postgresql start")
        print("       Windows: Start 'PostgreSQL' in Services")
        print(f"  2. Verify credentials in your .env file:")
        print(f"       DATABASE_URL={Config.SQLALCHEMY_DATABASE_URI}")
        print("  3. If using a different user/password, update DATABASE_URL in .env")
        sys.exit(1)


def create_tables(app):
    """Create all SQLAlchemy tables."""
    from models import db
    with app.app_context():
        db.create_all()
        print("  Tables created: courses, questions, summaries, test_sessions")


def drop_tables(app):
    """Drop all tables — DESTRUCTIVE."""
    from models import db
    with app.app_context():
        db.drop_all()
        print("  All tables dropped.")


def seed_sample_data(app):
    """Insert sample data so you can test the UI without uploading a PDF."""
    from models import db, Course, Question, Summary
    import random

    with app.app_context():
        # Check if seed data already exists
        if Course.query.filter_by(name='Biology 101 (Sample)').first():
            print("  Sample data already exists — skipping seed.")
            return

        course = Course(name='Biology 101 (Sample)', published=True)
        db.session.add(course)
        db.session.flush()

        sample_questions = [
            ("What is the powerhouse of the cell?", "Nucleus", "Mitochondria", "Ribosome", "Golgi apparatus", "B", "Mitochondria produce ATP via cellular respiration."),
            ("Which molecule carries genetic information?", "RNA", "ATP", "DNA", "Protein", "C", "DNA (deoxyribonucleic acid) stores hereditary information."),
            ("What process do plants use to make food?", "Respiration", "Fermentation", "Transpiration", "Photosynthesis", "D", "Photosynthesis converts sunlight and CO2 into glucose."),
            ("How many chromosomes does a normal human cell have?", "23", "44", "46", "48", "C", "Human somatic cells have 46 chromosomes in 23 pairs."),
            ("What is osmosis?", "Movement of solutes", "Movement of water across a membrane", "Active transport", "Cell division", "B", "Osmosis is the passive movement of water through a semipermeable membrane."),
        ]

        # Expand to 50 questions by cycling through samples
        for i in range(50):
            base = sample_questions[i % len(sample_questions)]
            q = Question(
                course_id=course.id,
                question=f"({i+1}) {base[0]}",
                option_a=base[1], option_b=base[2],
                option_c=base[3], option_d=base[4],
                correct_answer=base[5],
                explanation=base[6],
                approved=i < 40,  # First 40 are approved
            )
            db.session.add(q)

        summary = Summary(
            course_id=course.id,
            content="""
<div class="summary-content">
  <h2>Introduction to Cell Biology</h2>
  <p>The cell is the fundamental unit of life. All living organisms are composed of one or more cells.</p>

  <h3>Cell Organelles</h3>
  <ul>
    <li><strong>Mitochondria</strong>: The powerhouse of the cell — produces ATP via aerobic respiration.</li>
    <li><strong>Nucleus</strong>: Contains DNA and controls cell activities.</li>
    <li><strong>Ribosome</strong>: Site of protein synthesis.</li>
    <li><strong>Golgi apparatus</strong>: Processes and packages proteins for export.</li>
    <li><strong>Endoplasmic reticulum</strong>: Rough ER synthesises proteins; smooth ER synthesises lipids.</li>
  </ul>

  <h2>Genetics</h2>
  <p>Genetics is the study of heredity and variation in living organisms.</p>

  <h3>Key Concepts</h3>
  <ul>
    <li><strong>DNA</strong>: Double helix molecule carrying genetic instructions.</li>
    <li><strong>Chromosomes</strong>: Humans have 46 chromosomes (23 pairs).</li>
    <li><strong>Genes</strong>: Segments of DNA that code for specific proteins.</li>
    <li><strong>Alleles</strong>: Alternative forms of a gene.</li>
  </ul>

  <h2>Photosynthesis</h2>
  <p>Photosynthesis is the process by which green plants convert sunlight into chemical energy.</p>

  <h3>Equation</h3>
  <ul>
    <li>6CO2 + 6H2O + light energy → C6H12O6 + 6O2</li>
    <li>Occurs in the <strong>chloroplasts</strong></li>
    <li>Two stages: Light reactions and the Calvin cycle</li>
  </ul>

  <h2>Osmosis and Diffusion</h2>
  <ul>
    <li><strong>Diffusion</strong>: Movement of molecules from high to low concentration.</li>
    <li><strong>Osmosis</strong>: Diffusion of water across a semipermeable membrane.</li>
    <li><strong>Active transport</strong>: Movement against the concentration gradient — requires energy.</li>
  </ul>
</div>
""".strip()
        )
        db.session.add(summary)
        db.session.commit()

        print(f"  Sample course created: 'Biology 101 (Sample)' — published, 40 approved questions.")


def main():
    args = sys.argv[1:]
    do_reset = '--reset' in args
    do_seed  = '--seed'  in args

    print("\nCBT Mock AI — Database Setup")
    print("=" * 40)

    # Step 1: Create the database if it doesn't exist
    create_database_if_not_exists()

    # Step 2: Create the Flask app (which sets up SQLAlchemy)
    sys.path.insert(0, os.path.dirname(__file__))
    from app import create_app
    app = create_app()

    # Step 3: Optionally reset
    if do_reset:
        confirm = input("\nWARNING: --reset will delete ALL data. Type 'yes' to confirm: ").strip()
        if confirm.lower() != 'yes':
            print("Reset cancelled.")
            sys.exit(0)
        print("Dropping all tables...")
        drop_tables(app)

    # Step 4: Create tables
    print("Creating tables...")
    create_tables(app)

    # Step 5: Optionally seed
    if do_seed:
        print("Seeding sample data...")
        seed_sample_data(app)

    print("\nSetup complete.")
    print(f"  Database: {Config.SQLALCHEMY_DATABASE_URI}")
    print("  Run the server with: python app.py")
    if do_seed:
        print("  Sample course 'Biology 101 (Sample)' is ready to test.")
    print()


if __name__ == '__main__':
    main()

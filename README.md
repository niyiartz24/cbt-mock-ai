# CBT Mock AI

An AI-powered Computer-Based Testing and lesson summarisation platform. Admins upload PDF lesson notes; the system automatically generates MCQ questions and structured summaries. Students search for courses, take timed mock exams, and study AI-generated notes.

---

## Features

**Student side**
- Course search with instant results
- 40-question timed CBT (10 minutes, auto-submit)
- Per-question navigation with answered/unanswered indicators
- Instant graded results with correct answer highlights and explanations
- Structured AI lesson summaries with printable layout
- Dark / light mode toggle

**Admin side**
- Secure JWT login
- PDF upload with drag-and-drop
- Automatic AI question generation (50–60 MCQs per upload)
- Automatic AI lesson summary generation
- Full question editor (edit, delete, approve)
- One-click "Approve First 40" bulk action
- Summary HTML editor with live preview tab
- Publish / unpublish course control
- Platform statistics dashboard

---

## Tech Stack

| Layer    | Technology                          |
|----------|-------------------------------------|
| Backend  | Python · Flask · SQLAlchemy         |
| Database | PostgreSQL (prod) · SQLite (dev)    |
| AI       | OpenAI GPT-4o-mini                  |
| PDF      | PyMuPDF · pdfplumber (fallback)     |
| Frontend | Vanilla HTML · CSS · JavaScript     |
| Deploy   | Render (backend) · Vercel (frontend)|

---

## Project Structure

```
cbt-mock-ai/
├── backend/
│   ├── app.py                  # Flask app, all API routes
│   ├── config.py               # Configuration & env vars
│   ├── models.py               # SQLAlchemy database models
│   ├── wsgi.py                 # Gunicorn entry point
│   ├── requirements.txt
│   ├── render.yaml             # Render deployment config
│   ├── .env.example            # Environment variable template
│   └── utils/
│       ├── pdf_parser.py       # PDF text extraction
│       └── ai_service.py       # OpenAI question & summary generation
│
├── frontend/
│   ├── index.html              # Student homepage (search + actions)
│   ├── exam.html               # CBT exam engine
│   ├── summary.html            # Lesson summary viewer
│   ├── css/
│   │   └── style.css           # Full stylesheet (dark/light)
│   ├── js/
│   │   ├── config.js           # API base URL, storage, utilities
│   │   ├── main.js             # Homepage logic
│   │   ├── exam.js             # Exam engine logic
│   │   └── summary.js          # Summary page logic
│   └── admin/
│       ├── login.html          # Admin login
│       ├── dashboard.html      # Admin dashboard
│       └── admin.js            # Admin logic (in js/ folder)
│
├── vercel.json                 # Vercel frontend deployment
└── .gitignore
```

---

## Local Development Setup

### Prerequisites

- Python 3.10+
- PostgreSQL 14+ installed and running
- An OpenAI API key

### 1. Clone and enter the project

```bash
git clone https://github.com/your-username/cbt-mock-ai.git
cd cbt-mock-ai
```

### 2. Backend setup

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install all dependencies
pip install -r requirements.txt

# Create your .env file from the template
cp .env.example .env
```

### 3. Configure your .env

Open `backend/.env` and set these values:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cbt_mock
OPENAI_API_KEY=sk-your-key-here
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password
SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">
JWT_SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">
```

The `DATABASE_URL` format is: `postgresql://USER:PASSWORD@HOST:PORT/DBNAME`

If your local Postgres uses a different user or password, update accordingly.

### 4. Create the database and tables

```bash
# Basic setup — creates the DB and all tables
python setup_db.py

# OR with sample data (a published Biology course ready to test)
python setup_db.py --seed
```

The script will:
1. Connect to your local PostgreSQL
2. Create the `cbt_mock` database if it does not exist
3. Create all four tables: `courses`, `questions`, `summaries`, `test_sessions`
4. (With `--seed`) Insert a published sample course with 40 approved questions

### 5. Start the backend server

```bash
python app.py
# API available at: http://localhost:5000
```

### 6. Serve the frontend

No build step needed. From the project root:

```bash
# Python
cd frontend && python -m http.server 5500

# Node
npx serve frontend
```

Open `http://localhost:5500` in your browser.

### Common PostgreSQL setup commands

```bash
# macOS (Homebrew)
brew install postgresql@16
brew services start postgresql@16

# Ubuntu / Debian
sudo apt install postgresql postgresql-contrib
sudo service postgresql start

# Create a user and database manually (if setup_db.py cannot connect)
psql -U postgres
  CREATE USER myuser WITH PASSWORD 'mypassword';
  CREATE DATABASE cbt_mock OWNER myuser;
  \q
# Then set DATABASE_URL=postgresql://myuser:mypassword@localhost:5432/cbt_mock

# Reset the database (drops all data and recreates tables)
python setup_db.py --reset
```

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in:

| Variable          | Description                                      | Required |
|-------------------|--------------------------------------------------|----------|
| `SECRET_KEY`      | Flask session secret (generate randomly)         | Yes      |
| `JWT_SECRET_KEY`  | JWT signing secret (generate randomly)           | Yes      |
| `DATABASE_URL`    | PostgreSQL URL or leave default for SQLite       | Yes      |
| `OPENAI_API_KEY`  | Your OpenAI API key                              | Yes      |
| `ADMIN_USERNAME`  | Admin login username (default: `admin`)          | Yes      |
| `ADMIN_PASSWORD`  | Admin login password — change this               | Yes      |
| `CORS_ORIGINS`    | Allowed frontend origins (use `*` for dev)       | Yes      |
| `FLASK_ENV`       | `development` or `production`                    | No       |
| `JWT_EXPIRY_HOURS`| Token expiry in hours (default: 24)              | No       |
| `PORT`            | Server port (default: 5000)                      | No       |

Generate secure secrets with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## API Reference

All endpoints are prefixed with `/api`.

### Public endpoints

| Method | Endpoint                        | Description                            |
|--------|---------------------------------|----------------------------------------|
| GET    | `/health`                       | Health check                           |
| GET    | `/courses?q=<query>`            | Search published courses               |
| GET    | `/courses/<id>`                 | Get a single course                    |
| GET    | `/get-questions/<course_id>`    | Get 40 randomised exam questions       |
| POST   | `/submit-test`                  | Submit exam and receive graded results |
| GET    | `/get-summary/<course_id>`      | Get lesson summary for a course        |

### Auth

| Method | Endpoint           | Description        |
|--------|--------------------|--------------------|
| POST   | `/auth/login`      | Admin login → JWT  |
| GET    | `/auth/verify`     | Verify token       |

### Admin endpoints (JWT required)

| Method | Endpoint                                  | Description                    |
|--------|-------------------------------------------|--------------------------------|
| POST   | `/upload-pdf`                             | Upload PDF and trigger AI      |
| GET    | `/admin/courses`                          | All courses (draft + published)|
| DELETE | `/admin/courses/<id>`                     | Delete a course                |
| POST   | `/admin/courses/<id>/publish`             | Publish a course               |
| POST   | `/admin/courses/<id>/unpublish`           | Unpublish a course             |
| GET    | `/admin/courses/<id>/questions`           | Get all questions for a course |
| PUT    | `/admin/questions/<id>`                   | Edit a question                |
| DELETE | `/admin/questions/<id>`                   | Delete a question              |
| POST   | `/admin/questions/<id>/approve`           | Toggle question approval       |
| POST   | `/admin/courses/<id>/approve-all`         | Approve first 40 questions     |
| GET    | `/admin/courses/<id>/summary`             | Get summary (admin)            |
| PUT    | `/admin/courses/<id>/summary`             | Update summary HTML            |
| GET    | `/admin/stats`                            | Platform statistics            |

---

## Deployment

### Backend → Render

1. Push the `backend/` folder to a GitHub repository.
2. Create a new **Web Service** on [render.com](https://render.com).
3. Connect your repo. Render will detect `render.yaml` automatically.
4. Set the required environment variables in the Render dashboard:
   - `OPENAI_API_KEY`
   - `ADMIN_USERNAME`
   - `ADMIN_PASSWORD`
   - `CORS_ORIGINS` → your Vercel frontend URL
5. Deploy. Your API URL will be `https://your-service.onrender.com`.

### Frontend → Vercel

1. Update `frontend/js/config.js`:
   ```js
   const CONFIG = {
     API_BASE: 'https://your-service.onrender.com/api',
   };
   ```
2. Push the full repository to GitHub.
3. Import the project on [vercel.com](https://vercel.com).
4. Set the **Root Directory** to `frontend` (or use `vercel.json` at project root).
5. Deploy. Your app will be live at `https://your-project.vercel.app`.

---

## Admin Usage Guide

### First login
- Go to `/admin/login.html`
- Default credentials: `admin` / `admin123`
- **Change these immediately** via your `.env` file

### Uploading a course
1. Navigate to **Upload PDF** in the sidebar
2. Drag and drop or select a PDF (max 20MB, text-based)
3. Enter a course name (e.g. `Biology 101`)
4. Click **Upload and Generate**
5. Wait 30–60 seconds for AI processing

### Reviewing questions
1. Go to **Questions** and select your course
2. Review each generated question
3. Edit any that need improvement using the pencil icon
4. Click **Approve** on questions you want to keep
5. You need exactly 40 approved questions to publish
6. Use **Approve First 40** for a quick bulk action

### Publishing
1. Go to **Courses**
2. Ensure your course shows 40/40 approved questions and a summary
3. Click **Publish** — the course is now visible to students

---

## PDF Requirements

For best results, upload PDFs that:
- Are text-based (not scanned images)
- Contain at least 3–5 pages of content
- Use standard fonts and layouts
- Are not password-protected

If a PDF is image-based (scanned), text extraction will fail with a clear error message. Use an OCR tool to convert scanned PDFs to text-based PDFs before uploading.

---

## Edge Cases Handled

| Scenario                          | Handling                                                    |
|-----------------------------------|-------------------------------------------------------------|
| Scanned / image-only PDF          | Clear error: "unable to extract readable text"              |
| AI returns malformed JSON         | ValueError raised with context for debugging                |
| Fewer than 40 valid questions     | Warning returned; publish blocked until 40 approved         |
| Duplicate questions from AI       | Deduplicated during validation in `ai_service.py`           |
| PDF over 20MB                     | Rejected at upload with HTTP 413                            |
| Empty PDF                         | Rejected with "PDF has no pages" error                      |
| Student exam: fewer than 40 Q     | API returns 409 with helpful message                        |
| Token expired                     | 401 response, admin redirected to login                     |
| Large PDFs                        | Text chunked to 12,000 chars before sending to AI           |

---

## Local Database

During development, SQLite is used by default (`backend/cbt_mock.db`). All tables are created automatically on first run. Switch to PostgreSQL for production by setting `DATABASE_URL`.

---

## License

MIT License. Built by SynthaxLab.

EVA Restaurant
Professional Kitchen Display + Waiter Tablet + Accounting system  
Glassmorphism UI · فارسی · پښتو · English
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![Tests](https://img.shields.io/badge/tests-13%20passed-brightgreen.svg)
![License](https://img.shields.io/badge/license-Unlicense-lightgrey.svg)

> Clean multi-module architecture, centralized business rules, concurrent-safe SQLite (WAL), and unit tests for the critical invariants.
---
Architecture Overview
```
eva-restaurant/
├── main.py
├── eva_restaurant/
│   ├── core/                 # pure data + business rules (NO Qt)
│   │   ├── database.py       # models, WAL, is_locked, find_open_order, reports
│   │   └── __init__.py
│   ├── ui/                   # PySide6 only
│   │   ├── main_window.py
│   │   ├── styles.py
│   │   ├── widgets/
│   │   └── pages/
│   ├── server.py             # Flask API + SSE
│   ├── i18n/
│   └── logging/
├── templates/  static/  tests/  data/
├── pyproject.toml  requirements.txt  requirements-dev.txt
└── .github/workflows/ci.yml
```
Core has zero Qt imports. UI and the Flask server both consume the same business rules.
Design decisions (why this shape)
Decision	Rationale
Business rules only in `core/database.py` (`is_locked`, `find_open_order`, `OPEN_STATUSES`)	Desktop UI and Flask API can never diverge on order lifecycle
One open order per table enforced at the database layer	Two waiters cannot create parallel orders for the same table
Kitchen board is display + cook-status only	Clear separation of front-of-house vs kitchen responsibilities
SQLite + WAL + busy_timeout	Safe concurrent reads/writes from desktop + multiple tablets without a full Postgres setup
Items kept as JSON	Pragmatic for current scale; path to `order_items` table is documented for future growth
UI split into widgets + pages	1600-line monolith eliminated; each page is independently maintainable
---
Quick start
```bash
git clone <repo>
cd eva-restaurant
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
Waiter tablet: `http://<IP>:5050/`
Kitchen display (web): `http://<IP>:5050/kitchen`
Run tests
```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```
---
Synchronous analysis (components → coherent unit)
Single source of truth for order locking and “one open order per table”.
Role boundaries are enforced both in UI and in API.
API key required for every data-changing / data-reading endpoint.
Error handling is centralized; nothing fails silently.
Result: the system behaves as one coherent unit even though it consists of a desktop process + background Flask thread + multiple browser clients.
---
Diachronic analysis (will it stay solid over time?)
Growth scenario	Current behaviour	Risk	Mitigation already in place / next step
High daily order volume	Board limited to ~120 active tickets + indexes	Low for typical restaurant	Keep; optional cache later
Multi-year sales history	`sales_report_range` loads matching rows	Medium if tens of thousands of rows	Warning path + future SQL aggregation or Postgres
Concurrent tablets + desktop	WAL mode	Low	Already solved
Orphan food images	`delete_food_image` called on replace/delete	Closed	—
Backup while writes occur	`checkpoint_wal()` before copy	Closed	—
For a normal-to-medium restaurant the current design remains solid. The next scalability step (normalize items + optional Postgres) is intentionally left open and does not require rewriting the business rules.
---
Security notes
API key is generated once and compared with `secrets.compare_digest`.
Password for desktop settings is stored hashed.
CORS is enabled for local-network use; the API key is the real gate.
---
License
Unlicense — public domain. Use and modify freely.
---
Author
Built with real restaurant operational constraints in mind (concurrency, role separation, data integrity, live updates). Ready for further professional hardening (full test suite, CI, Postgres adapter).

---
Quality bar (what “done” means here)
Business rules live in one place and are unit-tested.
Server never trusts client-sent prices (`sanitize_items`).
One open order per table is enforced at the data layer.
Kitchen board cannot edit / deliver / cancel (role separation).
WAL + busy_timeout for concurrent desktop + tablets.
CI runs tests on Python 3.10 and 3.12.
Path to normalizing `order_items` is documented; current JSON storage is intentional for this scale.
Still intentional trade-offs (not defects):
Full GUI interaction tests are left to manual QA (PySide6 + display).
Sales aggregation is in-Python; for multi-year high-volume history move to SQL/Postgres.

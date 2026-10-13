# CarNab — car search and comparison

A Django marketplace-style search engine that keeps independent listings from Bama, Karnameh, Hamrah Mechanic, Khodro45, Divar and Sheypoor (it intentionally does **not** merge suspected duplicates), ranks Persian/English keyword queries, filters listings, and links buyers to the original seller page.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your local secret, LLM key, and deployment settings.
cd carfinder
python manage.py migrate
python manage.py seed_cars
python manage.py runserver
```

Open `http://127.0.0.1:8000`. The seeded data makes the interface useful immediately.

## Sync the local database to production

When you intentionally want the VPS to use your local SQLite data, run this from the project root:

```bash
./scripts/sync_db_to_server.sh
```

The script reads `VPS_HOST`, `VPS_USER`, `REMOTE_DB`, and `REMOTE_SERVICE` from the local `.env` (or the shell environment). It checks the local database, creates a timestamped backup on the VPS, uploads it, validates it again, and restarts the Django service. It uses SSH authentication; configure an SSH key rather than putting the VPS password in a script. The real `.env` is ignored by Git; only `.env.example` is committed.

Search is a two-step flow: a broad query such as `پژو ۲۰۶` first shows the distinct model/trim combinations present in the database; selecting a combination opens every matching listing with its source, price, year and outbound link. `/account/login/` and `/account/signup/` provide local Django authentication.

## Import / recrawl

```bash
python manage.py crawl_cars --source all
```

To refresh listings (marking missing cars inactive, detaching them from
comparison cards, and reactivating returning cars by image URL), run:

```bash
python manage.py recrawl_cars --source all
```

The same operation is scheduled every three hours with Celery Beat. Start a
Redis broker, then run `celery -A config.celery worker -l INFO` and
`celery -A config.celery beat -l INFO` from the `carfinder` directory.

The command fetches the public listing pages and upserts each source listing by its canonical source URL. Each marketplace has a separate crawler class in `cars/services.py`, because their card markup and URL patterns differ. It preserves listings from separate sources even when vehicle attributes match. Run it from cron, for example every 6 hours:

The crawler uses Playwright to scroll lazy-loaded pages and collects up to 500 distinct listings per selected source. Install its Chromium runtime once after installing dependencies:

```bash
playwright install chromium
export CRAWLER_HTTP_PROXY=http://127.0.0.1:2081
python manage.py crawl_cars --source hamrah --limit 500
```

After each crawl, listings are assigned to comparison cards by an exact normalized Persian/English title key. Unmatched listings are classified by the configured LLM in batches of 100; it may ignore non-car listings or create a cleaned new card title. The interface shows cards first; opening a card shows the source listings and each listing links out to its original marketplace page.

```cron
0 */6 * * * /path/to/.venv/bin/python /path/to/carfinder/manage.py crawl_cars --source all
```

To process existing cars without crawling again (for example after deleting all cards),
run the two visible phases separately. The default gateway model is `Qwen/Qwen3.8-27B`:

```bash
python manage.py extract_card_titles --output car_card_titles.json
python manage.py classify_car_cards --input car_card_titles.json --batch-size 100
```

Install the `openai` dependency from `requirements.txt` before using LLM matching. Set `LLM_BASE_URL`, `LLM_API_KEY`, and optionally `LLM_MODEL` in `.env`; never put the real key in source code.

Always make sure automated access complies with each source's terms and robots policy; the crawler identifies itself, throttles requests, and only reads public listing pages.

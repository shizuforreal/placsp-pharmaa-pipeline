# Your Complete Walkthrough — PLACSP Pharma Tender Pipeline

This document explains **everything**, from "what even is this project" to
"what do I say in the interview." Read it top to bottom once, then use it
as a checklist while you work.

---

## Part 1: What is this project, in plain English?

The company gave you a task: write a Python program that visits a Spanish
government website (where hospitals post "we want to buy medicine X"
notices), searches for 5 specific drugs, and saves what it finds into a
spreadsheet (CSV file).

I built you that program. It has 3 jobs:
1. **Search** the website for each drug name.
2. **Read** each result page and pull out facts (price, buyer, date, etc.).
3. **Save** all those facts into one CSV file.

The twist we discovered together: the website's search engine is "too
generous" — when you search "Fingolimod," it also returns giant contracts
that don't actually mention Fingolimod on the page itself (it's buried in
an attached PDF we're not supposed to open). So part of doing this well is
**explaining that limitation**, not hiding it. Companies doing take-homes
like this often care more about whether you *understood and explained* a
real-world messy problem than whether you got a perfect, huge spreadsheet.

---

## Part 2: One-time computer setup

You only do this once per computer.

### 2.1 Open the project in VS Code
- Unzip `placsp_pipeline.zip` somewhere easy to find, like your Desktop or Downloads.
- VS Code → File → Open Folder → select the unzipped `placsp_pipeline` folder.

### 2.2 Open a terminal inside VS Code
- Menu bar → Terminal → New Terminal.
- A black/dark panel opens at the bottom. This is where you type commands.

### 2.3 Confirm you're in the right folder
Type:
```
pwd
```
Press Enter. It should print a path ending in `.../placsp_pipeline` (NOT
`.../placsp_pipeline/pipeline`). If it's wrong, type `cd ..` and check
again.

### 2.4 Create a virtual environment
This is just a clean, isolated box for this project's Python packages.
```
python3 -m venv .venv
```

### 2.5 Activate it
```
source .venv/bin/activate
```
Your terminal prompt should now start with `(.venv)`. **You need to do
this every time you open a new terminal window for this project** (but
NOT redo step 2.4 — that's only once).

### 2.6 Install the required packages
```
pip install -r requirements.txt
```

You're now fully set up. ✅

---

## Part 3: Run the tests (proves the "brain" of the code works)

```
python -m pytest -v
```

You should see a list of test names ending in `PASSED`, and a final line
like `23 passed`. These tests don't use the internet — they check that the
logic (matching drug names, converting dates/prices) works correctly using
fake example data I wrote.

**If any test fails:** copy the error message and send it to me — don't
try to debug it alone.

---

## Part 4: Understand the 3 ways to get data

This project can get tender data three different ways. You'll mostly use
options 2 and 3 below, because option 1 (fully automatic) gives messy
results, as we discovered.

| # | Name | What it does | Command flag |
|---|------|--------------|---------------|
| 1 | Live search | Robot searches PLACSP itself | *(default, no flag needed)* |
| 2 | Seed URLs | You give it links you found by hand; it fetches & reads them | `--seed-urls` |
| 3 | Seed HTML | You give it pages you saved to your computer; fully offline | `--seed-html-manifest` |

### Why we need #2 and #3 at all
When the robot searches by itself (#1), PLACSP often returns huge
"framework agreement" contracts (think: "this contract covers 200 different
medicines") where your specific drug is only mentioned inside an attached
PDF — which we're not allowed to open per the assignment rules. So the
robot correctly says "molecule not found" for those. To get good, clean
rows, it's better to manually find smaller, specific tenders (like you did
for Abiraterone) and feed those in directly.

---

## Part 5: The full step-by-step process to build your final CSV

### Step 5.1 — Run live search to see what's out there (optional, informative)
```
python -m pipeline.run --output raw_search.csv
```
Wait for it to finish (it can take a few minutes — it deliberately goes
slowly so it doesn't overload the government server). This produces
`raw_search.csv` with everything the robot found by itself.

### Step 5.2 — Filter to only the trustworthy rows
```
python filter_detected.py raw_search.csv raw_search_filtered.csv
```
This keeps only rows where the drug name was actually found in the page
text (not buried in a PDF). Open `raw_search_filtered.csv` — these rows are
genuinely good, ready to use.

### Step 5.3 — Manually find more tenders for thin molecules
For any molecule with few/no rows after filtering, repeat what you did for
Abiraterone:
1. Go to PLACSP, search the molecule name (try both English and Spanish —
   e.g. "Tamsulosin" and "Tamsulosina").
2. Look through results for **specific, small tenders** — ones whose title
   literally contains the drug name — rather than giant "Acuerdo Marco"
   (framework agreement) listings covering hundreds of lots.
3. Click "Detalle de la licitación."
4. Copy the URL.
5. Send me the URL (or the page's text/HTML, like you did before) and I'll
   add it to `seed_urls.example.csv` (rename it to `seed_urls.csv` once you
   have your own list) and re-run the pipeline with it.

Repeat until you have a reasonable number of total rows (20-50 is the
brief's target — quality matters more than hitting an exact number).

### Step 5.4 — Run the pipeline with your manually-found URLs
```
python -m pipeline.run --output output.csv --no-live-search --seed-urls seed_urls.csv
```
(`--no-live-search` skips the noisy automatic search and uses only your
hand-picked URLs — cleaner for the final deliverable.)

### Step 5.5 — Sanity-check the final CSV
Open `output.csv`. For each row, check:
- Does `title` make sense and mention a real product?
- Is `awardValue` a real-looking number, not blank?
- Is `moleculeDetected` mostly `TRUE`?

If many rows look wrong or blank, send me the CSV and I'll help debug
`extract.py` again.

---

## Part 6: If something looks broken — debugging together

If a real page's data comes back blank/wrong, grab its raw HTML so I can
see exactly what the page looks like:

```
python debug_fetch_page.py "PASTE_THE_FULL_URL_HERE"
```

This saves `debug_page.html`. Open it in VS Code, copy a chunk of it
(especially around the field that's wrong, e.g. search for "Adjudicatario"
in the file with Cmd+F), and send it to me. I'll update `pipeline/extract.py`
to handle that layout.

---

## Part 7: Putting it on GitHub (the actual deliverable)

The brief asks for a GitHub repository. Here's how, assuming you don't
have git experience:

### 7.1 Create a GitHub account (if you don't have one)
Go to github.com, sign up.

### 7.2 Create a new repository
- Click the "+" top right → "New repository"
- Name it something like `placsp-pharma-pipeline`
- Choose Public or Private (either is fine per the brief)
- **Don't** check "Add a README" (we already have one)
- Click "Create repository"

### 7.3 Push your code (run these in your VS Code terminal, in the project folder)
GitHub will show you commands after creating the repo, but here's the
gist:
```
git init
git add .
git commit -m "Initial pipeline submission"
git branch -M main
git remote add origin PASTE_YOUR_REPO_URL_HERE
git push -u origin main
```

If `git` says it's not installed, tell me your operating system and I'll
give you install instructions.

### 7.4 Double check
Refresh your GitHub repo page in the browser — you should see all your
files: `pipeline/`, `tests/`, `README.md`, `output.csv`, etc.

---

## Part 8: Explaining your project (what they'll likely ask)

You said you want it to look like *you* did it — here's how to genuinely
own it: understand the reasoning below well enough to explain it in your
own words. You don't need to memorize code line-by-line; you need to
understand **why** each decision was made.

**Q: Walk me through your architecture.**
A: "I split it into separate files by responsibility: `molecules.py` holds
the drug names and their Spanish spelling variants. `http_client.py`
wraps `requests` so every web call automatically rate-limits itself and
retries on failure. `search.py` submits searches to the site. `extract.py`
reads a result page's HTML and pulls out fields like price and buyer.
`models.py` defines exactly what a row of my CSV looks like. `csv_writer.py`
writes it all out. `run.py` ties it together with command-line options."

**Q: What was the hardest part?**
A: "The website is a JSF/Liferay portal — an older type of website where
search results depend on hidden session state, not just a simple link. I
also found their search engine matches text inside attached PDF files, not
just the page itself, so a search for a specific drug sometimes returns
huge unrelated contracts where the drug is only named in an attachment.
Since the brief says we don't parse PDFs, my pipeline correctly marks
those as 'not detected' rather than pretending it found something it
didn't."

**Q: How did you handle errors / what happens if a page fails to load?**
A: "Every fetch and parse step is wrapped in error handling — if one page
fails, it logs a warning and skips that page, rather than crashing the
whole run. I also added retries with backoff for temporary network
errors, and a deliberate delay between requests so I'm not hammering a
public government server."

**Q: How did you test it?**
A: "I wrote unit tests against saved example HTML pages — not live
requests — so they run instantly and don't depend on the website being up.
They check that drug-name matching works (including Spanish spellings)
and that field extraction and data cleanup (dates, prices) work correctly."

**Q: Did you use AI?**
A: The brief explicitly says this is welcome. Be honest: "Yes, I worked
with Claude to design and build this, and I made sure to understand and
test every part — I can walk you through any file." This is a normal,
accepted answer for this kind of brief.

---

## Quick command cheat-sheet

```bash
# one-time setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# every time you open a new terminal
source .venv/bin/activate

# run tests
python -m pytest -v

# run pipeline (live search)
python -m pipeline.run --output raw_search.csv

# filter to confident matches only
python filter_detected.py raw_search.csv raw_search_filtered.csv

# run using your own manually-found URLs (recommended final run)
python -m pipeline.run --output output.csv --no-live-search --seed-urls seed_urls.csv

# debug one specific page
python debug_fetch_page.py "https://full-url-here"
```

---

If you get stuck anywhere in this document, tell me **which step number**
you're on and paste exactly what you see — I'll help immediately.

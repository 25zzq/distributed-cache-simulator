# Private internship assistant

This runs on your machine. It watches internship listings, keeps the ones that fit your resume, fills out each application from those facts, writes every application to a spreadsheet, and reads your inbox for interviews, assessments, rejections, and offers.

Your profile, resume, mailbox password, and application log stay in `data/`. That folder is gitignored.

The assistant does not invent jobs, GPA, sponsorship, or years of experience. If a required answer is not in your profile, it saves the application as needing your input and does not send it. An empty work history is written as no full-time experience.

## What it will send by itself

Email applications are the automatic path. When a listing has an apply-by-email address, your profile is filled in, your resume file is in place, and `auto_apply_email` is true, it sends the cover letter and resume from your mailbox. A daily cap stops it from sending more than you set.

Greenhouse, Lever, and Ashby publish job lists that this tool can read. Their application-submit APIs belong to the employer, so this tool does not post into those systems. For those roles it writes a filled packet you can paste into the form, saves the apply link, and puts the row on the sheet. After you submit the form, mark it:

```bash
python3 -m internship_assistant mark APPLICATION_ID applied
```

It will not bypass CAPTCHAs or log into a job site as you.

## Setup

```bash
pip install -r internship_assistant/requirements.txt
python3 -m internship_assistant init
```

Edit `data/profile.json`:

- Replace the sample name, school, projects, skills, and coursework with yours.
- Leave `experience` as `[]` if you have not had a job. Do not add roles you did not hold.
- Set `work_authorization` and `needs_sponsorship` yourself. Sponsorship is left blank until you do.
- Set `resume_path` to your resume file, for example `data/resume.pdf`.
- Set `"example": false` and `"needs_review": false` when the file is actually yours.

You can also start from a labeled text resume:

```bash
python3 -m internship_assistant import-resume my-resume.txt --force
```

The importer still sets `needs_review` to true so you can read it before anything is sent.

### Listings

`data/listings.json` holds roles you add by hand. New files you drop there are picked up on the next run. To follow public boards, add slugs to `data/config.json`:

```json
"boards": {
  "greenhouse": [{"token": "board-token-from-the-careers-url", "company": "Company"}],
  "lever": [{"site": "company-site", "company": "Company"}],
  "ashby": [{"board": "board-name", "company": "Company"}]
}
```

`json_feeds` and `rss_feeds` accept extra public feeds. `rss_feeds` entries look like `{"name": "Career center", "url": "https://..."}`.

### Email

For Gmail, turn on IMAP and create an App Password. Put the password in the environment, not in the config file:

```bash
export IMAP_PASSWORD="your-app-password"
export SMTP_PASSWORD="your-app-password"
```

In `data/config.json`, set `imap.username` and `smtp.username` to your address. Leave `auto_apply_email` false until a sample run looks right, then set it to true. `daily_apply_cap` defaults to 8.

### Google Sheet

The same rows are always written to `data/applications.csv`. To also update a Google Sheet:

1. Create a spreadsheet and add a sheet named `Applications` (or the name you set as `worksheet`).
2. Create a Google Cloud service account, enable the Sheets API, and download the JSON key to `data/google-service-account.json`.
3. Share the spreadsheet with the service account email as an editor.
4. Put the spreadsheet id (the long id in the sheet URL) in `google_sheet.spreadsheet_id`.

## Daily use

Open the dashboard, edit your profile or listings, and press Run search whenever you want another pass:

```bash
python3 -m internship_assistant dashboard
```

That starts a private page at http://127.0.0.1:8765. It does not accept connections from other computers. The same page lets you change the resume profile, add or edit listings, change the match score and email cap, read each filled packet, and set a status after you submit a form or hear back.

The command line does the same pass without the page:

```bash
python3 -m internship_assistant run
```

Either one reads listings, scores them, writes packets in `data/packets/`, sends allowed emails, checks the inbox, and updates the CSV and Google Sheet.

```bash
python3 -m internship_assistant stats
python3 -m internship_assistant inbox
python3 -m internship_assistant show APPLICATION_ID
python3 -m internship_assistant watch --interval 3600
```

`watch` repeats `run` until you stop it. A cron entry does the same thing:

```cron
0 8 * * * cd /path/to/this/repo && IMAP_PASSWORD=... SMTP_PASSWORD=... python3 -m internship_assistant run
```

## How a listing is counted

Roles that are not internships, co-ops, or new-grad postings are recorded as seen and skipped. So are senior titles and postings that require 3 or more years. Listings at or above `min_match_score` become applications. The report then shows how many were submitted, how many are waiting on you, and the response, interview, and offer rates among the ones that were actually sent or marked applied.

Match score uses your skills, project technologies, coursework, location, and interests. It does not reward years you did not list.

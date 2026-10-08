# SaansSaathi build plan (24 hours)

Clock starts **2026-10-08 17:18 IST**. Hard stop **2026-10-09 17:18 IST**.
Team: solo (Yashika + Claude Code). Region: `us-east-1`. Model: Claude Sonnet on Bedrock.

Rule: if a block runs more than 1 hour over its target, stop and cut scope.

## 1. Planner engine + CLI (target H5, 22:18 Oct 8). Done 17:23
- [x] `saans/forecast.py`: Open-Meteo hourly PM2.5/PM10, replay via `start_date`/`end_date`, cache in `fixtures/`
- [x] `saans/aqi.py`: CPCB NAQI sub-index, "AQI (est.)", pytest on every breakpoint edge
- [x] `saans/rules.py` + `config/rules.yaml`: bands 101–200 / 201–300 / 301–400 / 401+
- [x] `saans/planner.py`: per block keep / indoors / reschedule with reasons; impact in child-hours
- [x] `config/schools.json`: 3 demo schools (Anand Vihar, RK Puram, Dwarka)
- [x] `python -m saans.plan --school demo-1 --replay 2024-11-18` prints a full plan

## 2. Agent + voice + messaging, local (target H10, 03:18 Oct 9). Code done 17:27, live test waits on AWS creds + bot token
- [x] Strands agent on Bedrock, tools `get_forecast`, `compute_plan`, `get_school`
- [x] Writes principal summary (EN), parent message (HI, under 60 words), parent message (EN)
- [x] Template fallback when Bedrock fails
- [x] Polly `Kajal` neural, `hi-IN`, MP3 to S3
- [x] Telegram `Channel`: principal Approve/Skip, `/join DEMO1`, language pick, voice note on approve
- [x] Local long polling

## 3. Deploy with SAM (target H15, 08:18 Oct 9). Template + deploy script done 17:42, not deployed yet
- [x] `template.yaml`: daily Lambda, webhook Lambda, worker Lambda (async), DynamoDB single table, S3 audio, HTTP API, EventBridge Scheduler 05:30 IST Mon–Sat
- [x] Bot token in SSM Parameter Store, `.env.example`
- [x] `POST /run-now?school=demo-1&replay=2024-11-18`

## 4. Dashboard (target H19, 12:18 Oct 9, then feature freeze). Done locally 17:41 (plain HTML/JS)
- [x] One mobile-first page: plan card, AQI (est.) bar per school hour in CPCB colours, cleanest window, approval status, impact counter, "Run 5:30 AM check now" button
- [x] Hosted on S3 + CloudFront or Amplify Hosting

## 5. Submission (H19–H23, until 16:18 Oct 9)
- [ ] README: problem, users, how it works, Mermaid diagram, AWS services and why, setup, demo, limitations, attribution, AI-assistance disclosure
- [ ] `docs/demo-script.md`: 3-minute shot list
- [ ] `docs/blog-draft.md`
- [ ] Record demo video, publish repo, submit

## Not doing
Inbound voice Q&A, Transcribe, WhatsApp (unless everything is done), teacher messages, login/Cognito, multi-page dashboard, setup wizard, station bias correction.

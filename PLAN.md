# SaansSaathi build plan (24 hours)

Clock starts **2026-10-08 17:18 IST**. Hard stop **2026-10-09 17:18 IST**.
Team: solo (Yashika + Claude Code). Region: `us-east-1`. Model: Claude Sonnet on Bedrock.

Rule: if a block runs more than 1 hour over its target, stop and cut scope.

## 1. Planner engine + CLI (target H5, 22:18 Oct 8)
- [ ] `saans/forecast.py`: Open-Meteo hourly PM2.5/PM10, replay via `start_date`/`end_date`, cache in `fixtures/`
- [ ] `saans/aqi.py`: CPCB NAQI sub-index, "AQI (est.)", pytest on every breakpoint edge
- [ ] `saans/rules.py` + `config/rules.yaml`: bands 101–200 / 201–300 / 301–400 / 401+
- [ ] `saans/planner.py`: per block keep / indoors / reschedule with reasons; impact in child-hours
- [ ] `config/schools.json`: 3 demo schools (Anand Vihar, RK Puram, Dwarka)
- [ ] `python -m saans.plan --school demo-1 --replay 2024-11-18` prints a full plan

## 2. Agent + voice + messaging, local (target H10, 03:18 Oct 9)
- [ ] Strands agent on Bedrock, tools `get_forecast`, `compute_plan`, `get_school`
- [ ] Writes principal summary (EN), parent message (HI, under 60 words), parent message (EN)
- [ ] Template fallback when Bedrock fails
- [ ] Polly `Kajal` neural, `hi-IN`, MP3 to S3
- [ ] Telegram `Channel`: principal Approve/Skip, `/join DEMO1`, language pick, voice note on approve
- [ ] Local long polling

## 3. Deploy with SAM (target H15, 08:18 Oct 9)
- [ ] `template.yaml`: daily Lambda, webhook Lambda, worker Lambda (async), DynamoDB single table, S3 audio, HTTP API, EventBridge Scheduler 05:30 IST Mon–Sat
- [ ] Bot token in SSM Parameter Store, `.env.example`
- [ ] `POST /run-now?school=demo-1&replay=2024-11-18`

## 4. Dashboard (target H19, 12:18 Oct 9, then feature freeze)
- [ ] One mobile-first page: plan card, AQI (est.) bar per school hour in CPCB colours, cleanest window, approval status, impact counter, "Run 5:30 AM check now" button
- [ ] Hosted on S3 + CloudFront or Amplify Hosting

## 5. Submission (H19–H23, until 16:18 Oct 9)
- [ ] README: problem, users, how it works, Mermaid diagram, AWS services and why, setup, demo, limitations, attribution, AI-assistance disclosure
- [ ] `docs/demo-script.md`: 3-minute shot list
- [ ] `docs/blog-draft.md`
- [ ] Record demo video, publish repo, submit

## Not doing
Inbound voice Q&A, Transcribe, WhatsApp (unless everything is done), teacher messages, login/Cognito, multi-page dashboard, setup wizard, station bias correction.

# Demo video: 3-minute shot list

Setup before recording:
- Laptop: dashboard open (CloudFront URL), Demo School 1 selected, "Replay a past day" = 18 Nov 2024.
- Phone A (principal): Telegram, already sent `/principal DEMO1`.
- Phone B (parent): Telegram, already sent `/join DEMO1` and picked हिन्दी. Volume up.
- Do one full dry run first so Lambda and Bedrock are warm, then record.
- Screen-record the laptop; film both phones (or mirror them) for the phone shots.

| Time | Shot | Say (roughly) |
|---|---|---|
| 0:00–0:20 | **Problem.** A still of Delhi smog at a school morning, then the dashboard. | "In Delhi winters, the air is worst between 6 and 10 AM, exactly when kids are in assembly and PE. The afternoon is often far cleaner. A forecast number doesn't help a principal at 5:30 AM. A plan does." |
| 0:20–1:00 | **Dashboard, Run now.** Press "Run 5:30 AM check now" on the replay of 18 Nov 2024, a GRAP Stage IV day. Steps tick: forecast, rules + agent, waiting for approval. Plan card fills in; AQI (est.) bars in CPCB colours, cleanest hour ringed. | "This replays a real severe day. SaansSaathi pulls the hourly PM2.5 and PM10 forecast, converts it with CPCB breakpoints, and the rule engine decides: assembly indoors, Class 6–8 PE moved from 8:00 to 12:20, from 317 to 104, windows closed until 10. Every decision quotes its numbers." |
| 1:00–1:30 | **Principal phone.** Message arrives with the summary and Approve / Skip. Tap Approve. Message updates "Approved. Sending to N parents". | "The principal gets one message. The wording comes from a Strands agent on Bedrock, but the agent can't change any decision; the rules made them. One tap." |
| 1:30–2:00 | **Parent phone.** Hindi text arrives, then the voice note. Play it on camera. | "Parents get a short note in Hindi, and a voice note read by Amazon Polly's Kajal voice, because many parents would rather listen than read." |
| 2:00–2:40 | **Impact + AWS.** Back to the dashboard: status "Sent to parents", child-hours counter, parents reached. Then the architecture diagram from the README, and a quick look at the Lambda / EventBridge Scheduler console. | "Each approved plan adds to child-hours of outdoor activity moved out of bad air: 940 for this one school, this one morning. It runs on AWS: EventBridge Scheduler at 5:30 IST, Lambda, Bedrock with Strands Agents, Polly, DynamoDB and S3, all deployed with SAM." |
| 2:40–3:00 | **Close.** Dashboard on a phone screen. | "Forecasts already exist. SaansSaathi turns them into a decision a principal can make in one tap, and a message every parent can hear. Code is open source; link below." |

Backup if anything fails live: the template fallback still produces all three messages without Bedrock, and `python -m saans.plan --school demo-1 --replay 2024-11-18` prints the plan in a terminal.

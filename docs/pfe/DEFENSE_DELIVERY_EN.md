# Panopta PFE defense delivery

## Files to take to the presentation

- `output/pfe/Presentation_Panopta_PFE_English_Improved.pptx`
- `output/pfe/Demo_Panopta_PFE_Action.mp4`
- `docs/pfe/PRESENTATION_SCRIPT_EN.md`
- `docs/pfe/DEMO_SCRIPT_EN.md`
- `docs/pfe/DEFENSE_STUDY_GUIDE_EN.md`

Keep the PowerPoint and MP4 in the same folder. Slide 18 links to the video by filename. If PowerPoint blocks the link, open the MP4 directly before the defense.

## Recommended flow

1. Present slides 1 to 12 to establish the problem, architecture, execution model, database, and tenant isolation.
2. Follow slides 13 to 23 in order. The sequence matches the product flow from sources to governance.
3. Present the validation evidence on slide 24.
4. Start the silent video from slide 25 and speak from `DEMO_SCRIPT_EN.md`.
5. Finish with slide 26.

The full slide script contains approximately 1,600 words and takes about 11 minutes at a clear defense pace. The video is 3 minutes and 34 seconds. The complete flow is about 15 minutes before questions.

## Demonstration facts

- The workspace and e-commerce records are synthetic. No Oyster production data appears in the demo.
- The live PostgreSQL test succeeds.
- The profiled table contains 8,500 orders.
- `payment_status` reaches a 100 percent null rate in the injected incident scenario.
- The read-only SQL monitor returns 8,500 violations.
- The typed DSL monitor checks `null_rate` on `payment_status` against a threshold of `0.01`.
- The DSL rule is validated, compiled, activated as an immutable revision, queued, and persisted with a failed outcome.
- Incident analysis is AI-assisted. Probable causes are hypotheses for a person to verify.
- AI governance is an observe-only prototype. It does not certify compliance and does not block deployments.

## Rebuild and rerecord

Run the application with the seeded PFE workspace first. The recorder signs in as `mounir@acme.io`, prepares the verified schema snapshot, uses the real UI, and captures real API responses.

```bash
node scripts/pfe/record_action_demo.mjs
python3 scripts/pfe/export_action_video.py
node scripts/pfe/build_defense_en.mjs
```

For a fast browser rehearsal without recording a WebM file:

```bash
FAST=1 node scripts/pfe/record_action_demo.mjs
```

## Final checks before entering the room

- Open the PPTX once on the presentation computer.
- Confirm that both logos and all application screenshots render.
- Open the MP4 and confirm that it plays at 1920 by 1080.
- Turn off notifications and close personal tabs.
- Keep `DEFENSE_STUDY_GUIDE_EN.md` available on a second device.
- Never describe the AI governance prototype as a compliance certificate.

# Tweet Draft for Submission

## Option A (concise)

Built Hermes Dojo for the @NousResearch hackathon — a self-improvement system for Hermes Agent.

It reads your past sessions, finds where the agent fails, creates skills to fix those failures, and runs self-evolution (GEPA) on the weakest ones.

Your agent gets better while you sleep.

[video]

GitHub: https://github.com/Yonkoo11/hermes-dojo

## Option B (more technical)

"Why does my agent keep making the same mistakes?"

Built Hermes Dojo for the @NousResearch hackathon. It closes the feedback loop that makes self-evolution actually useful:

1. Reads session logs from state.db
2. Finds tool failures, retry loops, user corrections
3. Creates targeted skills with real bash commands and error handling
4. Runs GEPA self-evolution on weak skills
5. Delivers a morning report to Telegram

From seeded demo data: 57% → 85% after one Dojo cycle (your mileage will vary with real sessions).

GitHub: https://github.com/Yonkoo11/hermes-dojo

[video]

## Option C (shortest)

Hermes Dojo: your agent's overnight training gym.

Reads sessions → finds failures → creates skills → runs self-evolution → reports results.

Built for the @NousResearch hackathon.

[video] https://github.com/Yonkoo11/hermes-dojo

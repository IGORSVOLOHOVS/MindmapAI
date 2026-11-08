# Manual

```powershell
.\recipe.ps1 run
```

The bot takes no arguments. It reads `TELEGRAM_BOT_TOKEN` from the environment or from `.env` in the working folder, and finds `gemini` and `dot` on PATH.

## Commands in Telegram

| command | what the bot does |
| --- | --- |
| `/plan` | asks for a plan, then sends the plan to Gemini, which returns one `task | label` line per relevant task; the bot draws the labels as boxes joined in the order given and sends the PNG |
| `/ask` | asks for a question, then sends Gemini's answer, or `An error occurred: ...` with the CLI's error output |
| `/cancel` | ends the current `/plan` or `/ask` conversation |

A message outside a conversation gets a reminder of `/plan` and `/ask`.

## What `/plan` keeps

Gemini's lines are read one by one. A line without `|` is dropped, a line is split at its first `|`, and a line whose task or label is empty is dropped. When nothing is left, the bot asks the user to rephrase. When `dot` is not on PATH, the tasks come back as a `- task (label)` list.

Each node's tooltip holds the full task text; the box shows the short label.

## Running and stopping

- Ctrl+C stops the bot, and so does any normal end of polling.
- A crash is logged and the bot starts again after 15 seconds.
- A missing `gemini` or token ends the run with exit code 1, without a restart.
- Every run writes a new log file `mindmap-ai-<date>-<time>-<pid>.log` under `~/.mindmap-ai/logs`, or under the folder `MINDMAP_AI_LOG_DIR` names. The same lines go to the console.

The model is fixed in `app/bot.py` as `gemini-2.5-flash`.

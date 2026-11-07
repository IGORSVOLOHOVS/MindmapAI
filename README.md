# mindmap-ai

A Telegram bot that turns a written plan into a mind-map picture and answers questions, with the Google Gemini CLI doing the language work.

- **/plan** asks for a plan in free text. Gemini keeps only the actionable tasks and gives each a short label; the bot draws them as a chain of boxes with Graphviz and sends the PNG back. Without Graphviz's `dot` on the machine it sends the tasks as a text list instead.
- **/ask** passes a question straight to Gemini and sends back the answer.
- **/cancel** ends a `/plan` or `/ask` conversation.

Any other message gets a pointer to the two commands.

## Use

```powershell
.\recipe.ps1 run
```

The bot reads `TELEGRAM_BOT_TOKEN` from the environment or from a `.env` file in the working folder, and calls `gemini` and `dot` from PATH. It polls Telegram until it is stopped with Ctrl+C, restarts itself 15 seconds after a crash, and writes one log file per session under `~/.mindmap-ai/logs`.

`docs/install.md` says what to install and `docs/manual.md` describes every command. `.\recipe.ps1 test` runs the tests, mypy and ruff; the tests replace the Gemini CLI and Telegram with fakes, so they need neither the network nor a key.

## Licence

MIT, see `LICENSE`.

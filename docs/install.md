# Install

1. Install [uv](https://docs.astral.sh/uv/) and Python 3.13.
2. Clone this repository and run `uv sync --frozen` at its root. That installs `python-telegram-bot`, `python-dotenv`, `graphviz` and `httpx` at the versions `uv.lock` pins.
3. Install the Gemini CLI with `npm install -g @google/gemini-cli@latest` and sign it in once by running `gemini` by hand. `gemini-cli-install.sh` does the install on Linux.
4. Install Graphviz so that `dot` is on PATH (`winget install Graphviz.Graphviz`, `sudo apt install graphviz` or `brew install graphviz`). Without it `/plan` answers in text.
5. Create a bot with BotFather and put its token in a `.env` file at the root:

   ```env
   TELEGRAM_BOT_TOKEN="123456:your-token"
   ```

   `.env` is gitignored and never committed.

Start the bot with `.\recipe.ps1 run`. The console shows each start-up step: `gemini` found, `dot` found or not, the token read, and `Starting bot`. It stops with exit code 1 when `gemini` or the token is missing.

`.\recipe.ps1 build` packs the module into a wheel in `dist\`. The wheel installs a `mindmap-ai` command.

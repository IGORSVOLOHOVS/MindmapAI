# MindmapAI

A simple yet powerful **Python Telegram Bot** that leverages **Google's Gemini AI** to transform unstructured text plans into clear, visual mind maps and provides general AI-powered Q\&A functionality.

-----

## 🚀 Features

  * **AI-Powered Planning (`/plan`)**: Uses the **Gemini 2.5 Flash model** to analyze user text, filter out irrelevant details, and extract a clean list of actionable tasks suitable for a mind map.
  * **Visual Mind Map Generation**: Automatically converts the structured task list into a directional **mind map diagram** using the **Graphviz** library (`dot` utility).
  * **General Q\&A (`/ask`)**: Serves as a direct interface to the Gemini CLI for any general questions.
  * **Asynchronous & Robust**: Built on the modern `python-telegram-bot` framework with `asyncio`.
  * **Secure Configuration**: Uses the `.env` file for storing the sensitive Telegram Bot Token.

-----

## 📋 Prerequisites

Ensure the following components are installed on your system before setup:

1.  **Python 3.8+**
2.  **Google Gemini CLI**: The command-line interface for Google Gemini.
    ```bash
    npm install -g @google/gemini-cli@latest
    ```
3.  **Graphviz (`dot`)**: The underlying utility required by the `graphviz` Python library to generate PNG images from the diagram code. Install it via your system's package manager (e.g., `sudo apt install graphviz` on Debian/Ubuntu or `brew install graphviz` on macOS).

-----

## 🛠️ Installation and Setup

Follow these steps to get your bot up and running.

### 1\. Clone the Repository

```bash
git clone https://github.com/IGORSVOLOHOVS/MindmapAI.git
cd MindmapAI
```

### 2\. Install Python Dependencies

It is highly recommended to use a Python virtual environment.

```bash
# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows, use 'venv\Scripts\activate'

# Install project dependencies
pip install -r requirements.txt
```

The required dependencies are: `python-dotenv`, `python-telegram-bot`, `graphviz`, and `httpx`.

### 3\. Configure Environment Variables

The bot requires your Telegram Bot Token.

  - Create a file named `.env` in the root directory of the project.
  - Add your token in the following format:

**`.env`**

```env
# Environment variables for the Telegram Bot

# Get your token from BotFather on Telegram
TELEGRAM_BOT_TOKEN="YOUR:SUPER_SECRET_TELEGRAM_TOKEN"
```

*(Note: Your `.gitignore` file correctly ensures this file is not committed to Git.)*

-----

## ▶️ Running the Bot

Once all prerequisites and setup steps are complete, you can start the bot.

1.  Open your terminal in the project's root directory.
2.  Execute the main application file:

<!-- end list -->

```bash
python app/bot.py
```

You should see log output indicating that the bot has successfully loaded the token, checked for the necessary CLI tools (`gemini` and `dot`), set up the handlers, and started polling.

### ⏹️ Usage Commands

  * **/plan**: Starts a conversation to generate a mind map. Send the bot a list of tasks, to-dos, or a detailed plan. Gemini will filter and structure it, and the bot will send back a visual diagram.
  * **/ask**: Starts a conversation for a general question. The bot will pass your text directly to Gemini and return the full answer.
  * **/cancel**: Stops the current `/plan` or `/ask` conversation.

### ⚙️ Fallback

If the `dot` utility (Graphviz) is not found on your system, the bot will still process the plan using Gemini but will send the results back as a plain text list.

-----

## 📁 Project Structure

```
MindmapAI/
│
├── app/
│   └── bot.py              # Main Python bot logic and handlers
│
├── requirements.txt        # Python dependencies
├── gemini-cli-install.sh   # Helper script for installing gemini-cli
├── .env                    # Environment variables (secret)
└── .gitignore              # Ensures .env is ignored
```

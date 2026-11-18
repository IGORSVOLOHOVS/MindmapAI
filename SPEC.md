# MindmapAI - Software Requirements Specification

Reverse-engineered from the code at commit `c40f7e5` (branch `dev`) on 2026-11-18.
The code, not the README, is the reference: where the two differ, this document follows
the code and records the difference. Line references point to files in this checkout.
Statements about library behaviour come from reading the library sources installed on
the documenting machine (python-telegram-bot 22.6, python-dotenv 1.1.0). They are
labelled as such.

<!-- jira-sync:start -->
Jira: KAN-89

## Tasks

This list is one ticket in Jira project KAN, [KAN-89](https://igorsvolohovs.atlassian.net/browse/KAN-89). Each line is a checkbox there: tick it in Jira and the sync ticks it here; add a checkbox there and it is appended here. Done items are the features described in section 3; open items are what the project declares but the code does not do yet.

- [x] Startup and lifecycle (section 3.1) <!-- spec-startup-and-lifecycle -->
- [x] `/plan`: plan to diagram (section 3.2) <!-- spec-plan-plan-to-diagram -->
- [x] `/ask`: general question (section 3.3) <!-- spec-ask-general-question -->
- [x] Gemini CLI invocation (section 3.4) <!-- spec-gemini-cli-invocation -->
- [x] Other messages and errors (section 3.5) <!-- spec-other-messages-and-errors -->
- [ ] "directional mind map diagram" (declared, not implemented) <!-- spec-directional-mind-map-diagram -->
- [ ] Bot can be stopped with Ctrl+C ("Press Ctrl+C to stop", `except KeyboardInterrupt`) (declared, not implemented) <!-- spec-bot-can-be-stopped-with-ctrl-c-press-ctrl-c-to-sto -->
- [ ] Mermaid CLI and headless Chrome as installation steps (declared, not implemented) <!-- spec-mermaid-cli-and-headless-chrome-as-installation-st -->
- [ ] `python-telegram-bot[job-queue]` and `httpx` dependencies (declared, not implemented) <!-- spec-python-telegram-botjob-queue-and-httpx-dependencie -->
- [ ] `.env` shown as part of the project tree (declared, not implemented) <!-- spec-env-shown-as-part-of-the-project-tree -->

<!-- jira-sync:end -->

## 1. Purpose and scope

MindmapAI is a Telegram bot. It turns free-form plan text into a task diagram, and it
relays general questions to Google Gemini through the Gemini CLI.

In scope (implemented in `app/bot.py`):
- the `/plan` conversation: extract tasks with Gemini, render a PNG with Graphviz, or
  send a text list when Graphviz is missing;
- the `/ask` conversation: send the user's text to Gemini and return the answer;
- `/cancel`, a hint for stray text, and a global error handler;
- startup checks for `gemini`, `dot` and `TELEGRAM_BOT_TOKEN`, and a restart loop.

Out of scope (no code for it in this checkout):
- persistent storage;
- user accounts or access control;
- webhooks;
- a direct Gemini API client;
- Mermaid rendering (Haskell v1.0.1 sent Mermaid text and v1.0.2 rendered it with
  `mmdc`, before v2.0.0);
- deployment tooling and tests.

## 2. Context

| Actor / system | Role | Evidence |
|---|---|---|
| Telegram user | Sends `/plan`, `/ask`, `/cancel` and text; receives text and PNG messages | `app/bot.py:373-396` |
| Telegram Bot API | Reached through `python-telegram-bot` long polling | `app/bot.py:360-367`, `app/bot.py:401` |
| Gemini CLI (`gemini`) | Local executable started once per request | `app/bot.py:107-124` |
| Google Gemini service | Called by the Gemini CLI, not by `bot.py` (inference from the CLI's role; the repo does not configure it) | `README.md:22-24` |
| Graphviz `dot` | Local executable used by the `graphviz` Python package to render PNG | `app/bot.py:83`, `README.md:26` |

Runtime environment:
- Python, version "3.8+" per `README.md:21`.
- Node.js/npm, needed to install the Gemini CLI (`README.md:24`).
- Graphviz, optional (`README.md:26`).
- The OS is not specified. The README gives activation commands for both POSIX and
  Windows (`README.md:48`) and Graphviz install commands for Debian/Ubuntu and macOS
  (`README.md:26`).
- No hardware requirements are stated.

## 3. Functional requirements

All verification entries read "no test", because this checkout contains no automated
tests.

### 3.1 Startup and lifecycle

- **FR-1.** The system shall load environment variables from a `.env` file at startup.
  Source: `app/bot.py:326`. Verification: no test.
- **FR-2.** The system shall look up `gemini` on `PATH`. If it is not found, the system
  shall log an error with the install command and return from `main()` without polling.
  Source: `app/bot.py:329-335`. Verification: no test.
- **FR-3.** The system shall look up `dot` on `PATH`. If it is not found, the system
  shall log a warning and continue in text-fallback mode. The result is stored in
  `bot_data['dot_path']`. Source: `app/bot.py:340-347`, `app/bot.py:369`.
  Verification: no test.
- **FR-4.** The system shall read `TELEGRAM_BOT_TOKEN` from the environment. If it is
  missing, the system shall log an error and return from `main()` without polling.
  Source: `app/bot.py:350-355`. Verification: no test.
- **FR-5.** The system shall build the Telegram application with these HTTP timeouts:
  connect 60 s, read 300 s, write 300 s. It shall then start long polling.
  Source: `app/bot.py:360-367`, `app/bot.py:401`. Verification: no test.
- **FR-6.** The system shall call `main()` in an endless loop, with these rules:
  - after `main()` returns normally, call it again at once;
  - after an exception, log at CRITICAL level and call it again after 15 s;
  - leave the loop only when `KeyboardInterrupt` reaches the top level.

  Source: `app/bot.py:403-412`. Verification: no test. The consequences are described
  in `docs/README.md`, section 8, items 2 and 3.

### 3.2 `/plan`: plan to diagram

- **FR-7.** On `/plan`, the system shall reply "What is your plan? (for mind-map
  generation)" with a `/cancel` hint, and wait for one text message.
  Source: `app/bot.py:191-200`, `app/bot.py:375`, `app/bot.py:379-381`.
  Verification: no test.
- **FR-8.** On a non-command text message while waiting for a plan, the system shall:
  - send a status message;
  - insert the text into a fixed prompt. The prompt asks Gemini to drop irrelevant
    phrases and to return lines of the form `Full Task Name | LABEL`;
  - send that prompt to the Gemini CLI.

  Source: `app/bot.py:213-228`, `app/bot.py:133-157`. Verification: no test.
- **FR-9.** The system shall parse Gemini's output line by line. It shall keep only the
  lines that contain `|`, split each at the first `|` into task and label, and drop pairs
  where either part is empty after trimming. Source: `app/bot.py:165-175`.
  Verification: no test.
- **FR-10.** In each of these cases the system shall reply "Could not find any relevant
  tasks in your plan. Please try rephrasing.":
  - the Gemini CLI exits with a non-zero code;
  - its output is empty;
  - no pair is parsed.

  Source: `app/bot.py:159-161`, `app/bot.py:180-182`, `app/bot.py:241-246`.
  Verification: no test.
- **FR-11.** For the parsed pairs, the system shall build a directed Graphviz graph:
  - one box node per task, numbered from 1 in output order;
  - the node label is the short label, and the `tooltip` is the full task text;
  - one edge from each node to the next one.

  Source: `app/bot.py:45-60`. Verification: no test.
- **FR-12.** If `dot` was found at startup, the system shall:
  - send "Generating diagram...";
  - render the graph to a PNG in the system temporary directory;
  - send the PNG as a photo;
  - delete the temporary files afterwards, also when an error occurs.

  Source: `app/bot.py:233-235`, `app/bot.py:62-103`. Verification: no test.
- **FR-13.** If rendering or sending the PNG raises an exception, the system shall reply
  "Error generating PNG: <exception text>". Source: `app/bot.py:92-97`.
  Verification: no test.
- **FR-14.** If `dot` was not found at startup, the system shall reply with the heading
  "Tasks filtered (Graphviz 'dot' not found, sending as text):", followed by one line
  `- <task> (<label>)` per pair. Source: `app/bot.py:236-240`. Verification: no test.
- **FR-15.** The system shall end the `/plan` conversation after one reply cycle.
  Source: `app/bot.py:248`. Verification: no test.

### 3.3 `/ask`: general question

- **FR-16.** On `/ask`, the system shall reply "What is your question?" with a `/cancel`
  hint, and wait for one text message. Source: `app/bot.py:202-211`, `app/bot.py:376`,
  `app/bot.py:382-384`. Verification: no test.
- **FR-17.** The system shall send a status message, then pass the received text
  unchanged as the Gemini CLI prompt. Source: `app/bot.py:258-264`.
  Verification: no test.
- **FR-18.** The system shall reply with Gemini's stdout when the exit code is 0 and
  stdout is not empty. Otherwise it shall reply "An error occurred: <stderr>", or
  "An error occurred: Unknown CLI error." when stderr is empty. It shall then end the
  conversation. Source: `app/bot.py:266-276`. Verification: no test.

### 3.4 Gemini CLI invocation

- **FR-19.** The system shall run `gemini -m gemini-2.5-flash -p <prompt>` as a
  subprocess without a shell. It shall capture stdout and stderr, decode them, strip
  them, and return them together with the exit code. Source: `app/bot.py:30`,
  `app/bot.py:107-124`. Verification: no test.
- **FR-20.** The system shall map launch failures to exit code -1 with these messages:
  - executable missing: `Error: 'gemini' utility not found. Please install it.`;
  - any other exception: `Internal server error while calling Gemini: <e>`.

  Source: `app/bot.py:126-131`. Verification: no test.

### 3.5 Other messages and errors

- **FR-21.** On `/cancel` during a conversation, the system shall reply "Action
  cancelled." and end the conversation. Source: `app/bot.py:278-285`, `app/bot.py:386`.
  Verification: no test.
- **FR-22.** On a non-command text message outside a conversation, the system shall
  reply with a hint that names `/plan` and `/ask`. Source: `app/bot.py:289-302`,
  `app/bot.py:391-396`. Verification: no test.
- **FR-23.** On an unhandled exception in any handler, the system shall:
  - log the exception with its traceback;
  - if the update has a chat, send "Sorry, an internal error occurred. I have logged it
    and am continuing to run.";
  - if that send fails, log the failure.

  Source: `app/bot.py:306-317`, `app/bot.py:398`. Verification: no test.

### 3.6 Declared but not implemented

| Claim | Where | What the code does |
|---|---|---|
| "directional **mind map** diagram" | `README.md:10` | Produces a linear chain: node *i* has one edge to node *i+1* (`app/bot.py:49`). There is no branching or hierarchy. |
| Bot can be stopped with Ctrl+C ("Press Ctrl+C to stop", `except KeyboardInterrupt`) | `app/bot.py:400`, `app/bot.py:407-409` | Inference, not run: PTB 22.6 `run_polling` catches `KeyboardInterrupt` itself and returns. FR-6 then calls `main()` again. |
| Mermaid CLI and headless Chrome as installation steps | `gemini-cli-install.sh:18-33` | The Python bot does not use Mermaid. This is a leftover from Haskell v1.0.2, which added this part of the script and called `mmdc` (`git show 7b7dda9:app/Main.hs`, lines 121-128, 166). |
| `python-telegram-bot[job-queue]` and `httpx` dependencies | `requirements.txt:2`, `requirements.txt:4` | No JobQueue is used. `httpx` is imported but never used (`app/bot.py:27`). |
| `.env` shown as part of the project tree | `README.md:113` | `.env` is not tracked; `.gitignore:1` excludes it. |

## 4. Interfaces

### 4.1 Telegram commands and messages

| Input | State | Handler | Output |
|---|---|---|---|
| `/plan` | any (entry point) | `plan_start` (`app/bot.py:191`) | prompt text; state `WAITING_PLAN_MINDMAP` |
| `/ask` | any (entry point) | `ask_start` (`app/bot.py:202`) | prompt text; state `WAITING_QUESTION` |
| text, not a command | `WAITING_PLAN_MINDMAP` | `plan_receive_mindmap` (`app/bot.py:213`) | status message, then a PNG photo, a text list or "no tasks"; conversation ends |
| text, not a command | `WAITING_QUESTION` | `ask_receive_question` (`app/bot.py:250`) | status message, then the answer or an error; conversation ends |
| `/cancel` | inside a conversation | `cancel` (`app/bot.py:278`) | "Action cancelled." |
| text, not a command | no conversation | `handle_general_message` (`app/bot.py:289`) | hint |
| `/start`, other commands, non-text messages | any | none | no reply (no handler matches; `app/bot.py:373-396`) |

The bot has no HTTP endpoints of its own. It uses long polling and opens no listening
port (`app/bot.py:401`).

### 4.2 External processes

| Process | Invocation | Expected output | Source |
|---|---|---|---|
| Gemini CLI | `gemini -m gemini-2.5-flash -p <prompt>` (argv list, no shell) | `/plan`: lines `Full Task Name \| LABEL`; `/ask`: free text on stdout | `app/bot.py:108`, `app/bot.py:140` |
| Graphviz | `graphviz.Digraph.render(filename=<tmp>.png, format='png', cleanup=True)` | `<tmp>.png.png` | `app/bot.py:83-86` |

### 4.3 Command line

`python app/bot.py` (`README.md:86`). The program takes no arguments or flags; nothing in
`app/bot.py` parses arguments.

## 5. Data

| Entity | Storage | Format / lifetime | Source |
|---|---|---|---|
| Bot token | `TELEGRAM_BOT_TOKEN` env var, usually from `.env` | string; never written by the bot | `app/bot.py:350` |
| Conversation state | PTB `ConversationHandler`, in memory | keyed per chat and per user (PTB defaults `per_chat=True`, `per_user=True`); lost on restart | `app/bot.py:373-387` |
| `dot_path` | `application.bot_data`, in memory | path or `None` | `app/bot.py:369` |
| Task list | in memory, per request | `List[Tuple[task, label]]` | `app/bot.py:165` |
| Diagram files | system temporary directory | `<tmp>.png`, created by `NamedTemporaryFile(delete=False)` and passed to `render` as the file name with `cleanup=True`, and `<tmp>.png.png`, the image the code opens and sends; both deleted in `finally` if present | `app/bot.py:80-103` |
| Log | stderr (`logging.basicConfig` default) | `%(asctime)s - %(name)s - %(levelname)s - %(message)s`, INFO level; includes the full user text and Gemini's raw output | `app/bot.py:36-39`, `app/bot.py:134`, `app/bot.py:163` |

There is no database and no persistent file written by the bot.

## 6. Non-functional requirements

- **NFR-1 (timeouts, Telegram).** The Telegram HTTP client uses connect 60 s, read 300 s
  and write 300 s. Source: `app/bot.py:363-365`.
- **NFR-2 (timeouts, Gemini).** Gemini CLI calls have no time limit: `communicate()` is
  awaited without a timeout. Source: `app/bot.py:117`.
- **NFR-3 (restart).** After an exception escapes `main()`, the process waits 15 s and
  restarts. When `main()` returns normally, there is no delay. Source:
  `app/bot.py:403-412`.
- **NFR-4 (concurrency).** Updates are processed one at a time. This is inference: the
  PTB 22.6 builder defaults to `SimpleUpdateProcessor(max_concurrent_updates=1)`, and
  `bot.py` does not call `concurrent_updates()`. Source: `app/bot.py:360-367`.
- **NFR-5 (secrets).** The token is read from the environment or `.env`, and `.env` is
  excluded from git. Source: `app/bot.py:350`, `.gitignore:1`.
- **NFR-6 (process safety).** User text reaches the Gemini CLI as a single argv element
  through `create_subprocess_exec`. It is never interpreted by a shell. Source:
  `app/bot.py:108-116`.
- **NFR-7 (access).** There is no allow-list or user check, so any Telegram user can use
  the bot. Source: `app/bot.py:191-302` (no user filter in any handler).
- **NFR-8 (fallback).** Without Graphviz, `/plan` still answers, in text form. Source:
  `app/bot.py:236-240`.
- **NFR-9 (encoding).** CLI output is decoded with `bytes.decode()`, which defaults to
  strict UTF-8. Output that is not valid UTF-8 raises an exception, and FR-20 maps it to
  an "Internal server error" result. Source: `app/bot.py:119-120`, `app/bot.py:129-131`.

## 7. Constraints and dependencies

Python packages (`requirements.txt`). There is no lock file, so versions are resolved
at install time:

| Package | Constraint |
|---|---|
| `python-dotenv` | unpinned |
| `python-telegram-bot[job-queue]` | `>=20.0` |
| `graphviz` | unpinned |
| `httpx` | unpinned |

On the documenting machine, PTB 22.6 declares `Requires-Python: >=3.10` and
`httpx>=0.27,<0.29` (its installed `METADATA`). With the README's "Python 3.8+", pip
will therefore select different PTB versions on different interpreters.

External tools:
- `@google/gemini-cli@latest`, installed with npm (`README.md:24`,
  `gemini-cli-install.sh:6`). Unpinned.
- Graphviz `dot` (`README.md:26`).
- Optionally, through `gemini-cli-install.sh:23-24`: `@mermaid-js/mermaid-cli@latest` and
  `chrome-headless-shell`. The bot does not use them.

Code-level constraints:
- The model name is fixed in code (`app/bot.py:30`).
- The prompt language and format are fixed in code (`app/bot.py:136-155`).
- The bot's replies are in English.

Licence: MIT (`LICENSE`).

## 8. Acceptance

There are no automated tests in this checkout. Acceptance is manual, against a real bot
token and a working Gemini CLI. None of these checks were performed while writing this
document.

| Check | Expected | Covers |
|---|---|---|
| Start with `TELEGRAM_BOT_TOKEN` unset | log `[ERROR] TELEGRAM_BOT_TOKEN variable not found in .env`; no polling | FR-4, FR-6 |
| Start with `gemini` not on `PATH` | log ``[ERROR] `gemini` utility not found in your PATH...``; no polling | FR-2, FR-6 |
| Start with `dot` not on `PATH` | warning logged; bot polls | FR-3 |
| `/plan`, then the example text from `app/bot.py:143` | status messages, then a PNG of boxes in a chain | FR-7 to FR-12, FR-15 |
| Same, without `dot` | text list `- <task> (<label>)` | FR-14 |
| `/plan`, then `hello, thanks` | "Could not find any relevant tasks..." (depends on the model's output) | FR-10 |
| `/ask`, then a question | Gemini's answer as text | FR-16 to FR-18 |
| `/plan` or `/ask`, then `/cancel` | "Action cancelled." | FR-21 |
| Plain text with no conversation | hint naming `/plan` and `/ask` | FR-22 |

## 9. Open questions

1. **Users.** Who is the bot for, and is it meant to be public? There is no access
   control (NFR-7).
2. **Gemini authentication.** How is the Gemini CLI supposed to authenticate in
   deployment: an API key in the environment, or an interactive Google login? The
   repository has nothing on this.
3. **Deployment.** Where and how is the bot deployed (host, OS, service manager)? The
   repository has no deployment files.
4. **Python version.** Which Python version is supported? The README says 3.8+, while
   current PTB needs 3.10+ and `requirements.txt` does not pin it.
5. **Diagram shape.** Is the diagram meant to be a linear chain, or a tree/mind map as
   the README says?
6. **Long answers.** What should happen to `/ask` answers longer than one Telegram
   message, and to Gemini calls that hang (NFR-2)?
7. **Stopping the bot.** Is `Ctrl+C` meant to stop the process? See the item on FR-6 in
   section 3.6.
8. **Mermaid in the install script.** Is the Mermaid part of `gemini-cli-install.sh`
   still wanted?
9. **Leftover settings.** Answered by the history: the `dist-newstyle/` and
   `cabal-project.local` entries in `.gitignore` were in the first commit 6fae27f, next
   to `haskell-gemini-bot.cabal`. They are cabal build outputs, and cabal left the
   repository in 847e0fd. Still unknown: the purpose of `.vscode/settings.json` excluding
   `**/target` (added in f480174, v1.0.1).
10. **Which branch is current.** Is `dev` still maintained? `origin/release` (revision
    4.0.0, 2026-11-08) contains this commit plus tests, CI and a different `app/bot.py`,
    and this specification describes only `dev` at `c40f7e5`.

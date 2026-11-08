"""Tests for app/bot.py: the mind map, the Gemini CLI wrapper, the handlers and the start-up.

Nothing here reaches the network or a paid API: the Gemini CLI is replaced by a fake
`asyncio.create_subprocess_exec`, Telegram by objects that record what the bot sends,
and Graphviz rendering by a graph that writes its own PNG under the system temp folder.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import bot
import pytest
from telegram import Update
from telegram.ext import ConversationHandler


class FakeProcess:
    def __init__(self, returncode: int | None, stdout: str, stderr: str = "") -> None:
        self.returncode = returncode
        self._out = stdout.encode()
        self._err = stderr.encode()

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._out, self._err


def fake_gemini(monkeypatch: pytest.MonkeyPatch, returncode: int | None, stdout: str, stderr: str = "") -> list:
    calls: list = []

    async def create(*args: str, **kwargs: Any) -> FakeProcess:
        calls.append(args)
        return FakeProcess(returncode, stdout, stderr)

    monkeypatch.setattr(bot.asyncio, "create_subprocess_exec", create)
    return calls


def fake_update(text: str | None = "hello", chat_id: int | None = 42, user_id: int | None = 7) -> MagicMock:
    update = MagicMock(spec=Update)
    update.effective_chat = SimpleNamespace(id=chat_id) if chat_id is not None else None
    update.effective_user = SimpleNamespace(id=user_id) if user_id is not None else None
    if text is None:
        update.message = None
    else:
        update.message = SimpleNamespace(text=text, reply_text=AsyncMock())
    return update


def fake_context(dot_path: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        bot=SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock()),
        bot_data={"dot_path": dot_path},
        error=None,
    )


def sent_texts(context: SimpleNamespace) -> list[str]:
    return [call.kwargs["text"] for call in context.bot.send_message.await_args_list]


# --- build_mind_map ---


def test_mind_map_chains_the_tasks_in_order() -> None:
    graph = bot.build_mind_map([("go to the store", "Go to Store"), ("buy milk", "Buy Milk"), ("walk dog", "Walk")])
    source = graph.source
    assert 'label="Go to Store"' in source and 'tooltip="go to the store"' in source
    assert "1 -> 2" in source and "2 -> 3" in source
    assert "1 -> 3" not in source and "3 -> 1" not in source
    assert "shape=box" in source


def test_mind_map_of_one_task_has_no_edge() -> None:
    assert "->" not in bot.build_mind_map([("only", "Only")]).source


# --- call_gemini_cli ---


def test_gemini_cli_gets_the_model_and_the_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_gemini(monkeypatch, 0, "  answer \n", " warn ")
    assert asyncio.run(bot.call_gemini_cli("question")) == (0, "answer", "warn")
    assert calls == [("gemini", "-m", bot.GEMINI_MODEL, "-p", "question")]


def test_gemini_cli_with_no_return_code_reports_minus_one(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_gemini(monkeypatch, None, "x")
    assert asyncio.run(bot.call_gemini_cli("q"))[0] == -1


def test_gemini_cli_missing_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    async def missing(*args: str, **kwargs: Any) -> FakeProcess:
        raise FileNotFoundError("gemini")

    monkeypatch.setattr(bot.asyncio, "create_subprocess_exec", missing)
    code, out, err = asyncio.run(bot.call_gemini_cli("q"))
    assert (code, out) == (-1, "") and "not found" in err


def test_gemini_cli_other_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(*args: str, **kwargs: Any) -> FakeProcess:
        raise OSError("boom")

    monkeypatch.setattr(bot.asyncio, "create_subprocess_exec", broken)
    code, _, err = asyncio.run(bot.call_gemini_cli("q"))
    assert code == -1 and "boom" in err


# --- get_mindmap_tasks_from_gemini ---


def test_plan_output_is_parsed_into_task_label_pairs(monkeypatch: pytest.MonkeyPatch) -> None:
    output = "go to the store | Go to Store\nnoise without a bar\nbuy milk | Buy | Milk\n | empty task\nwalk dog |  \n"
    calls = fake_gemini(monkeypatch, 0, output)
    tasks = asyncio.run(bot.get_mindmap_tasks_from_gemini("go to the store, buy milk"))
    assert tasks == [("go to the store", "Go to Store"), ("buy milk", "Buy | Milk")]
    prompt = calls[0][-1]
    assert '"go to the store, buy milk"' in prompt and "TASK | LABEL" in prompt


@pytest.mark.parametrize(("returncode", "stdout"), [(1, "a | A"), (0, ""), (0, "nothing useful here")])
def test_plan_with_failure_or_no_tasks_gives_none(
    monkeypatch: pytest.MonkeyPatch, returncode: int, stdout: str
) -> None:
    fake_gemini(monkeypatch, returncode, stdout, "err")
    assert asyncio.run(bot.get_mindmap_tasks_from_gemini("text")) is None


# --- reply_with_mind_map ---


class RenderingGraph:
    """Stands in for graphviz.Digraph: render() writes <filename>.png as dot would."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.rendered: list[str] = []

    def render(self, filename: str, format: str, cleanup: bool) -> str:
        if self.fail:
            raise RuntimeError("dot crashed")
        assert format == "png" and cleanup
        Path(f"{filename}.png").write_bytes(b"\x89PNG")
        self.rendered.append(filename)
        return f"{filename}.png"


def test_mind_map_is_sent_as_a_photo_and_the_files_are_removed() -> None:
    graph, context = RenderingGraph(), fake_context()
    asyncio.run(bot.reply_with_mind_map(fake_update(), context, graph))  # type: ignore[arg-type]
    assert context.bot.send_photo.await_count == 1
    assert context.bot.send_photo.await_args.kwargs["chat_id"] == 42
    base = graph.rendered[0]
    assert not Path(base).exists() and not Path(f"{base}.png").exists()


def test_render_failure_is_told_to_the_user() -> None:
    context = fake_context()
    asyncio.run(bot.reply_with_mind_map(fake_update(), context, RenderingGraph(fail=True)))  # type: ignore[arg-type]
    assert context.bot.send_photo.await_count == 0
    assert any("dot crashed" in text for text in sent_texts(context))


def test_mind_map_without_a_chat_sends_nothing() -> None:
    context = fake_context()
    asyncio.run(bot.reply_with_mind_map(fake_update(chat_id=None), context, RenderingGraph()))  # type: ignore[arg-type]
    assert context.bot.send_message.await_count == 0


# --- the conversation handlers ---


def test_plan_and_ask_start_ask_for_input_and_move_state() -> None:
    update = fake_update()
    assert asyncio.run(bot.plan_start(update, fake_context())) == bot.WAITING_PLAN_MINDMAP  # type: ignore[arg-type]
    assert asyncio.run(bot.ask_start(update, fake_context())) == bot.WAITING_QUESTION  # type: ignore[arg-type]
    assert update.message.reply_text.await_count == 2


def test_handlers_without_a_message_end_the_conversation() -> None:
    update, context = fake_update(text=None), fake_context()
    for handler in (bot.plan_start, bot.ask_start, bot.cancel, bot.plan_receive_mindmap, bot.ask_receive_question):
        assert asyncio.run(handler(update, context)) == ConversationHandler.END  # type: ignore[arg-type]
    asyncio.run(bot.handle_general_message(update, context))  # type: ignore[arg-type]
    assert context.bot.send_message.await_count == 0


def test_cancel_ends_the_conversation() -> None:
    update = fake_update(user_id=None)
    assert asyncio.run(bot.cancel(update, fake_context())) == ConversationHandler.END  # type: ignore[arg-type]
    update.message.reply_text.assert_awaited_once_with("Action cancelled.")


def test_plan_with_dot_renders_the_mind_map(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_gemini(monkeypatch, 0, "buy milk | Buy Milk\nwalk dog | Walk Dog")
    reply = AsyncMock()
    monkeypatch.setattr(bot, "reply_with_mind_map", reply)
    context = fake_context(dot_path="/usr/bin/dot")
    assert asyncio.run(bot.plan_receive_mindmap(fake_update("my plan"), context)) == ConversationHandler.END  # type: ignore[arg-type]
    graph = reply.await_args.args[2]
    assert 'label="Buy Milk"' in graph.source and "1 -> 2" in graph.source


def test_plan_without_dot_falls_back_to_text(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_gemini(monkeypatch, 0, "buy milk | Buy Milk")
    context = fake_context(dot_path=None)
    asyncio.run(bot.plan_receive_mindmap(fake_update("my plan"), context))  # type: ignore[arg-type]
    assert "- buy milk (Buy Milk)" in sent_texts(context)[-1]
    assert context.bot.send_photo.await_count == 0


def test_plan_with_no_tasks_asks_to_rephrase(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_gemini(monkeypatch, 0, "")
    context = fake_context(dot_path="/usr/bin/dot")
    asyncio.run(bot.plan_receive_mindmap(fake_update("hi"), context))  # type: ignore[arg-type]
    assert "rephrasing" in sent_texts(context)[-1]


def test_ask_returns_the_answer_or_the_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_gemini(monkeypatch, 0, "Paris")
    context = fake_context()
    asyncio.run(bot.ask_receive_question(fake_update("capital of France?"), context))  # type: ignore[arg-type]
    assert sent_texts(context)[-1] == "Paris" and calls[0][-1] == "capital of France?"

    fake_gemini(monkeypatch, 2, "", "quota exceeded")
    asyncio.run(bot.ask_receive_question(fake_update("again"), context))  # type: ignore[arg-type]
    assert sent_texts(context)[-1] == "An error occurred: quota exceeded"

    fake_gemini(monkeypatch, 2, "", "")
    asyncio.run(bot.ask_receive_question(fake_update("again"), context))  # type: ignore[arg-type]
    assert sent_texts(context)[-1] == "An error occurred: Unknown CLI error."


def test_a_message_outside_a_conversation_points_at_the_commands() -> None:
    context = fake_context()
    asyncio.run(bot.handle_general_message(fake_update("hey"), context))  # type: ignore[arg-type]
    assert "/plan" in sent_texts(context)[0] and "/ask" in sent_texts(context)[0]


def test_error_handler_tells_the_user_and_survives_a_failed_send() -> None:
    context = fake_context()
    context.error = ValueError("bad")
    update = MagicMock(spec=Update)
    update.effective_chat = SimpleNamespace(id=5)
    asyncio.run(bot.error_handler(update, context))  # type: ignore[arg-type]
    assert "internal error" in sent_texts(context)[0]

    context.bot.send_message.side_effect = RuntimeError("telegram down")
    asyncio.run(bot.error_handler(update, context))  # type: ignore[arg-type]

    asyncio.run(bot.error_handler(object(), fake_context()))  # type: ignore[arg-type]


def test_user_id_of_tolerates_an_update_without_a_user() -> None:
    assert bot.user_id_of(fake_update(user_id=9)) == 9
    assert bot.user_id_of(fake_update(user_id=None)) is None


# --- main and run_forever ---


class FakeApplication:
    def __init__(self) -> None:
        self.bot_data: dict = {}
        self.handlers: list = []
        self.error_handlers: list = []
        self.polled = False

    def add_handler(self, handler: object) -> None:
        self.handlers.append(handler)

    def add_error_handler(self, handler: object) -> None:
        self.error_handlers.append(handler)

    def run_polling(self) -> None:
        self.polled = True


class FakeBuilder:
    def __init__(self, application: FakeApplication) -> None:
        self.application = application
        self.settings: dict = {}

    def token(self, value: str) -> "FakeBuilder":
        self.settings["token"] = value
        return self

    def connect_timeout(self, value: float) -> "FakeBuilder":
        self.settings["connect"] = value
        return self

    def read_timeout(self, value: float) -> "FakeBuilder":
        self.settings["read"] = value
        return self

    def write_timeout(self, value: float) -> "FakeBuilder":
        self.settings["write"] = value
        return self

    def build(self) -> FakeApplication:
        return self.application


def prepare_main(monkeypatch: pytest.MonkeyPatch, tools: dict[str, str], token: str | None) -> FakeBuilder:
    monkeypatch.setattr(bot, "load_dotenv", lambda: None)
    monkeypatch.setattr(bot.shutil, "which", lambda name: tools.get(name))
    if token is None:
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    else:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    builder = FakeBuilder(FakeApplication())
    monkeypatch.setattr(bot, "ApplicationBuilder", lambda: builder)
    return builder


def test_main_wires_the_handlers_and_polls(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = prepare_main(monkeypatch, {"gemini": "/bin/gemini", "dot": "/bin/dot"}, "123:abc")
    assert bot.main() == 0
    application = builder.application
    assert application.polled and application.bot_data == {"dot_path": "/bin/dot"}
    assert builder.settings == {"token": "123:abc", "connect": 60.0, "read": 300.0, "write": 300.0}
    conversation = application.handlers[0]
    assert isinstance(conversation, ConversationHandler)
    commands = {command for entry in conversation.entry_points for command in entry.commands}  # type: ignore[attr-defined]
    assert commands == {"plan", "ask"}
    assert len(application.handlers) == 2 and application.error_handlers == [bot.error_handler]


def test_main_without_dot_still_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = prepare_main(monkeypatch, {"gemini": "/bin/gemini"}, "123:abc")
    assert bot.main() == 0 and builder.application.bot_data == {"dot_path": None}


def test_main_stops_without_gemini_or_token(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = prepare_main(monkeypatch, {}, "123:abc")
    assert bot.main() == 1 and not builder.application.polled
    builder = prepare_main(monkeypatch, {"gemini": "/bin/gemini"}, None)
    assert bot.main() == 1 and not builder.application.polled


def test_run_forever_restarts_after_a_crash_and_ends_on_a_clean_stop() -> None:
    outcomes: list = [RuntimeError("network"), RuntimeError("again"), 0]
    slept: list[float] = []

    def bot_main() -> int:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    assert bot.run_forever(bot_main, slept.append) == 0
    assert slept == [15, 15] and outcomes == []


def test_run_forever_ends_on_ctrl_c_and_on_a_missing_setup() -> None:
    def interrupted() -> int:
        raise KeyboardInterrupt

    assert bot.run_forever(interrupted, lambda seconds: None) == 0
    assert bot.run_forever(lambda: 1, lambda seconds: None) == 1


# --- logging ---


def test_each_session_gets_its_own_log_file(tmp_path: Path) -> None:
    root = logging.getLogger()
    saved, level = list(root.handlers), root.level
    try:
        first = bot.configure_logging(tmp_path / "logs", datetime(2026, 1, 2, 3, 4, 5))
        bot.logger.info("first session")
        second = bot.configure_logging(tmp_path / "logs", datetime(2026, 1, 2, 3, 4, 6))
        bot.logger.info("second session")
        for handler in root.handlers:
            handler.flush()
        assert first != second and first.name.startswith("mindmap-ai-20260102-030405")
        assert "first session" in first.read_text(encoding="utf-8")
        assert "second session" not in first.read_text(encoding="utf-8")
        assert "second session" in second.read_text(encoding="utf-8")
        assert len(root.handlers) == 2
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()
        for handler in saved:
            root.addHandler(handler)
        root.setLevel(level)


def test_log_dir_follows_the_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MINDMAP_AI_LOG_DIR", str(tmp_path))
    assert bot.default_log_dir() == tmp_path
    monkeypatch.delenv("MINDMAP_AI_LOG_DIR")
    assert bot.default_log_dir() == Path.home() / ".mindmap-ai" / "logs"

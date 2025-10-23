#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import shutil
import asyncio
import tempfile
import re
import time
from functools import partial, reduce
from typing import List, Optional, Tuple

import graphviz
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    ConversationHandler,
    filters,
)
import httpx

# --- Constants ---
GEMINI_MODEL: str = "gemini-2.5-flash"

# States for ConversationHandler
WAITING_PLAN_MINDMAP, WAITING_QUESTION = range(2)

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- Core Graphviz Functions ---

def build_mind_map(tasks_with_labels: List[Tuple[str, str]]) -> graphviz.Digraph:
    logger.info(f"Building mind map for {len(tasks_with_labels)} tasks.")
    
    nodes = [(i, task, label) for i, (task, label) in enumerate(tasks_with_labels, 1)]
    edges = list(zip([i for i, _, _ in nodes], [j for j, _, _ in nodes][1:]))
    
    dot = graphviz.Digraph(comment='Mind Map')
    dot.attr('node', shape='box')

    for i, task, label in nodes:
        dot.node(str(i), label=label, tooltip=task)
        
    for source, target in edges:
        dot.edge(str(source), str(target))
        
    return dot

async def reply_with_mind_map(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    graph: graphviz.Digraph
):
    if not update.effective_chat:
        logger.warning("No effective_chat found in update")
        return

    chat_id = update.effective_chat.id
    logger.info(f"Attempting to generate and send mind map to {chat_id}")

    try:
        await context.bot.send_message(
            chat_id=chat_id, 
            text="Generating diagram..."
        )
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tf:
            png_path = tf.name
        
        graph.render(filename=png_path, format='png', cleanup=True)
        
        logger.info(f"Graphviz render complete. Sending photo: {png_path}.png")
        with open(f"{png_path}.png", 'rb') as photo_file:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo_file
            )
            
    except Exception as e:
        logger.error(f"Error generating or sending PNG: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Error generating PNG: {e}"
        )
    finally:
        if 'png_path' in locals():
            if os.path.exists(f"{png_path}.png"):
                os.remove(f"{png_path}.png")
            if os.path.exists(png_path):
                os.remove(png_path)

# --- Core Gemini Functions ---

async def call_gemini_cli(prompt: str) -> Tuple[int, str, str]:
    cmd_args = ["gemini", "-m", GEMINI_MODEL, "-p", prompt]
    logger.info(f"Calling Gemini CLI with prompt: '{prompt[:70]}...'")
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout_bytes, stderr_bytes = await process.communicate()
        
        stdout = stdout_bytes.decode().strip()
        stderr = stderr_bytes.decode().strip()
        returncode = process.returncode if process.returncode is not None else -1

        logger.info(f"Gemini CLI: code={returncode}, stdout={stdout[:100]}..., stderr={stderr}")
        return returncode, stdout, stderr

    except FileNotFoundError:
        logger.error("Gemini CLI 'gemini' not found!")
        return -1, "", "Error: 'gemini' utility not found. Please install it."
    except Exception as e:
        logger.error(f"Error calling Gemini CLI: {e}")
        return -1, "", f"Internal server error while calling Gemini: {e}"

async def get_mindmap_tasks_from_gemini(text: str) -> Optional[List[Tuple[str, str]]]:
    logger.info(f"Crafting prompt for Gemini (mind map) filtering. Input: '{text}'")
    
    prompt = f"""You are a planning assistant. Your job is to extract ONLY RELEVANT tasks for a plan from the user's text.
    
1. Filter out junk: remove greetings, thanks, irrelevant phrases (like "ate well", "need to think") and keep only specific actions.
2. For each task, create a very short, human-readable label (e.g., "Go to Store", "Buy Milk", "Project Deadline").
3. Return the result STRICTLY in the format "Full Task Name | LABEL". Each task on a new line.

Example Request:
go to the store, buy milk, walk the dog, eat lunch, work project (deadline)

Example Response:
go to the store | Go to Store
buy milk | Buy Milk
walk the dog | Walk Dog
work project (deadline) | Project Deadline

MANDATORY: Do not add anything extra, only the "TASK | LABEL" list. If there are no relevant tasks, return an empty response.

User text to process:
"{text}"
"""
    
    returncode, stdout, stderr = await call_gemini_cli(prompt)
    
    if returncode != 0 or not stdout:
        logger.error(f"Gemini (plan) CLI error: {stderr or 'No output'}")
        return None

    logger.info(f"Gemini (plan) raw output:\n{stdout}")
    
    tasks_with_labels: List[Tuple[str, str]] = []
    try:
        lines = stdout.strip().split('\n')
        for line in lines:
            if '|' in line:
                parts = line.split('|', 1)
                if len(parts) == 2:
                    task = parts[0].strip()
                    label = parts[1].strip()
                    if task and label:
                        tasks_with_labels.append((task, label))
    except Exception as e:
        logger.error(f"Failed to parse Gemini (plan) response: {e}\nRaw: {stdout}")
        return None
        
    if not tasks_with_labels:
        logger.warning("Gemini (plan) returned a valid but empty list of tasks.")
        return None
        
    logger.info(f"Parsed tasks for diagram: {tasks_with_labels}")
    return tasks_with_labels

# --- Telegram Handlers ---

# 1. Conversation Handlers

async def plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the /plan conversation."""
    if not update.message:
        return ConversationHandler.END
        
    logger.info(f"User {update.message.from_user.id} initiated /plan command.")
    await update.message.reply_text(
        "What is your plan? (for mind-map generation)\nSend /cancel to stop."
    )
    return WAITING_PLAN_MINDMAP

async def ask_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the /ask conversation."""
    if not update.message:
        return ConversationHandler.END
        
    logger.info(f"User {update.message.from_user.id} initiated /ask command.")
    await update.message.reply_text(
        "What is your question?\nSend /cancel to stop."
    )
    return WAITING_QUESTION

async def plan_receive_mindmap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the plan text for mind-map generation."""
    if not update.message or not update.message.text or not update.effective_chat:
        return ConversationHandler.END
        
    chat_id = update.effective_chat.id
    text = update.message.text
    dot_path = context.bot_data.get('dot_path')
    
    logger.info(f"Handling /plan response from {chat_id}: '{text[:50]}...'")
    await context.bot.send_message(
        chat_id=chat_id,
        text="🧠 Analyzing plan and filtering tasks with Gemini..."
    )
    
    tasks_with_labels = await get_mindmap_tasks_from_gemini(text)
    
    if tasks_with_labels:
        mind_map_graph = build_mind_map(tasks_with_labels)
        
        if dot_path:
            logger.info("Valid tasks found. Generating mind map image...")
            await reply_with_mind_map(update, context, mind_map_graph)
        else:
            logger.warning("Valid tasks found, but 'dot' is not installed. Sending text fallback.")
            reply_text = "Tasks filtered (Graphviz 'dot' not found, sending as text):\n"
            reply_text += "\n".join([f"- {task} ({label})" for task, label in tasks_with_labels])
            await context.bot.send_message(chat_id=chat_id, text=reply_text)
    else:
        logger.info("Gemini processing for /plan resulted in no tasks.")
        await context.bot.send_message(
            chat_id=chat_id,
            text="Could not find any relevant tasks in your plan. Please try rephrasing."
        )
        
    return ConversationHandler.END

async def ask_receive_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the question for a general Gemini query."""
    if not update.message or not update.message.text or not update.effective_chat:
        return ConversationHandler.END
        
    chat_id = update.effective_chat.id
    text = update.message.text
    
    logger.info(f"Handling /ask response from {chat_id}: '{text[:50]}...'")
    await context.bot.send_message(
        chat_id=chat_id,
        text="🧠 Thinking about your question..."
    )
    
    returncode, stdout, stderr = await call_gemini_cli(text)
    
    reply_text = (
        stdout if returncode == 0 and stdout
        else f"An error occurred: {stderr or 'Unknown CLI error.'}"
    )
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=reply_text
    )
        
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    if not update.message:
        return ConversationHandler.END
        
    logger.info(f"User {update.message.from_user.id} cancelled conversation.")
    await update.message.reply_text("Action cancelled.")
    return ConversationHandler.END

# 2. General Message Handler (for non-command chat)

async def handle_general_message(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE
):
    """Handles all non-command messages outside of a conversation."""
    if not update.message or not update.message.text or not update.effective_chat:
        return
        
    logger.info(f"Received unhandled message from {update.effective_chat.id}.")

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="I'm not sure what you mean. Please use /plan to create a mind map or /ask to ask a question."
    )

# 3. Reliability Error Handler

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log Errors and send a warning message to the user."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Sorry, an internal error occurred. I have logged it and am continuing to run."
            )
        except Exception as e:
            logger.error(f"Failed to even send error message to user: {e}")


# --- Main Entry Point ---

def main() -> None:
    logger.info("--- Starting Python (FP) Gemini AI Bot ---")

    logger.info("0. Loading variables from .env file...")
    load_dotenv()

    logger.info("1. Checking for `gemini-cli`...")
    gemini_path = shutil.which("gemini")
    if not gemini_path:
        logger.error(
            "[ERROR] `gemini` utility not found in your PATH. "
            "Install it: npm install -g @google/gemini-cli@latest"
        )
        return
    else:
        logger.info(f"   `gemini` found: {gemini_path}")

    logger.info("1.1. Checking for `dot` (Graphviz)...")
    dot_path = shutil.which("dot")
    if not dot_path:
        logger.warning(
            "[WARNING] `dot` utility not found. "
            "Diagrams will not be generated for /plan (text fallback only)."
        )
    else:
        logger.info(f"   `dot` found: {dot_path}")

    logger.info("2. Getting Telegram token...")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error(
            "[ERROR] TELEGRAM_BOT_TOKEN variable not found in .env"
        )
        return

    logger.info("   (Using TELEGRAM_BOT_TOKEN variable from .env file)")
    
    logger.info("2.1. Creating HTTP client with 5-minute timeout...")
    application = (
        ApplicationBuilder()
        .token(token)
        .connect_timeout(60.0)
        .read_timeout(300.0)
        .write_timeout(300.0)
        .build()
    )

    application.bot_data['dot_path'] = dot_path

    logger.info("3. Setting up handlers...")

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('plan', plan_start),
            CommandHandler('ask', ask_start)
        ],
        states={
            WAITING_PLAN_MINDMAP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, plan_receive_mindmap)
            ],
            WAITING_QUESTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_receive_question)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    application.add_handler(conv_handler)
    
    application.add_handler(
        MessageHandler(
            filters.TEXT & (~filters.COMMAND), 
            handle_general_message
        )
    )
    
    application.add_error_handler(error_handler)

    logger.info("4. Starting bot... (Press Ctrl+C to stop)")
    application.run_polling()

if __name__ == "__main__":
    while True:
        try:
            main()
        except KeyboardInterrupt:
            logger.info("Bot stopped by user (Ctrl+C). Exiting.")
            break
        except Exception as e:
            logger.critical(f"CRITICAL ERROR in main loop: {e}. Restarting in 15 seconds...")
            time.sleep(15)
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import shutil
import asyncio
import tempfile
import re
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
    filters,
)
import httpx

GEMINI_MODEL: str = "gemini-2.5-flash"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def build_mind_map(tasks_with_abbrs: List[Tuple[str, str]]) -> graphviz.Digraph:
    logger.info(f"Building mind map for {len(tasks_with_abbrs)} tasks.")
    
    nodes = [(i, task, abbr) for i, (task, abbr) in enumerate(tasks_with_abbrs, 1)]
    
    edges = list(zip([i for i, _, _ in nodes], [j for j, _, _ in nodes][1:]))
    
    dot = graphviz.Digraph(comment='Mind Map')
    dot.attr('node', shape='box')

    for i, task, abbr in nodes:
        dot.node(str(i), label=abbr, tooltip=task)
        
    for source, target in edges:
        dot.edge(str(source), str(target))
        
    return dot

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

async def process_plan_with_gemini(text: str) -> Optional[List[Tuple[str, str]]]:
    logger.info(f"Crafting prompt for Gemini plan filtering. Input: '{text}'")
    
    user_text = text.replace("/plan", "").strip()
    if not user_text:
        logger.warning("Empty /plan command received.")
        return None

    prompt = f"""You are a planning assistant. Your job is to extract ONLY RELEVANT tasks for a plan from the user's text.
    
1. Filter out junk: remove greetings, thanks, irrelevant phrases (like "ate well", "need to think") and keep only specific actions.
2. For each task, create a very short, human-readable label (e.g., "Go to Store", "Buy Milk", "Project Deadline").
3. Return the result STRICTLY in the format "Full Task Name | LABEL". Each task on a new line.

Example Request:
/plan go to the store, buy milk, walk the dog, eat lunch, work project (deadline)

Example Response:
go to the store | Go to Store
buy milk | Buy Milk
walk the dog | Walk Dog
work project (deadline) | Project Deadline

MANDATORY: Do not add anything extra, only the "TASK | LABEL" list. If there are no relevant tasks, return an empty response.

User text to process:
"{user_text}"
"""
    
    returncode, stdout, stderr = await call_gemini_cli(prompt)
    
    if returncode != 0 or not stdout:
        logger.error(f"Gemini (plan) CLI error: {stderr or 'No output'}")
        return None

    logger.info(f"Gemini (plan) raw output:\n{stdout}")
    
    tasks_with_abbrs: List[Tuple[str, str]] = []
    try:
        lines = stdout.strip().split('\n')
        for line in lines:
            if '|' in line:
                parts = line.split('|', 1)
                if len(parts) == 2:
                    task = parts[0].strip()
                    abbr = parts[1].strip()
                    if task and abbr:
                        tasks_with_abbrs.append((task, abbr))
    except Exception as e:
        logger.error(f"Failed to parse Gemini (plan) response: {e}\nRaw: {stdout}")
        return None
        
    if not tasks_with_abbrs:
        logger.warning("Gemini (plan) returned a valid but empty list of tasks.")
        return None
        
    logger.info(f"Parsed tasks for diagram: {tasks_with_abbrs}")
    return tasks_with_abbrs


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


async def handle_message(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message or not update.message.text or not update.effective_chat:
        return
        
    chat_id = update.effective_chat.id
    text = update.message.text
    logger.info(f"Received message from chat {chat_id}: '{text[:100]}...'")

    dot_path = context.bot_data.get('dot_path')
    
    if text.strip().startswith("/plan"):
        logger.info("Handling /plan command...")
        await context.bot.send_message(
            chat_id=chat_id,
            text="🧠 Analyzing plan and filtering tasks with Gemini..."
        )
        
        tasks_with_abbrs = await process_plan_with_gemini(text)
        
        if tasks_with_abbrs:
            mind_map_graph = build_mind_map(tasks_with_abbrs)
            
            if dot_path:
                logger.info("Valid tasks found. Generating mind map image...")
                await reply_with_mind_map(update, context, mind_map_graph)
            else:
                logger.warning("Valid tasks found, but 'dot' is not installed. Sending text fallback.")
                reply_text = "Tasks filtered (Graphviz 'dot' not found, sending as text):\n"
                reply_text += "\n".join([f"- {task} ({abbr})" for task, abbr in tasks_with_abbrs])
                await context.bot.send_message(chat_id=chat_id, text=reply_text)
        
        else:
            logger.info("Gemini processing for /plan resulted in no tasks.")
            await context.bot.send_message(
                chat_id=chat_id,
                text="Could not find any relevant tasks in your plan. Please try rephrasing."
            )
            
    else:
        logger.info("Handling general message with Gemini...")
        await context.bot.send_message(
            chat_id=chat_id,
            text="🧠 Thinking about your request..."
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

    application.add_handler(
        MessageHandler(
            filters.TEXT & (~filters.COMMAND) | filters.Regex(r'^\/plan'), 
            handle_message
        )
    )

    logger.info("3. Starting bot... (Press Ctrl+C to stop)")
    application.run_polling()

if __name__ == "__main__":
    main()
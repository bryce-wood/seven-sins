"""
agent_engine.py
Shared engine for a single-domain coach agent.
Handles memory, chat loop, and memory extraction.
Agent-specific files (e.g. gluttony.py) import run_agent() and input their name and persona.
"""

import os
import sys
import json
import time
import importlib
import tempfile
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from google import genai

DEFAULT_MODEL = "gemini-3.6-flash"
EXTRACTION_MODEL = "gemini-3.6-flash" # meant to be the strongest (or stronger) model, ran once per session

BUILT_AGENTS = ["gluttony", "greed", "wrath", "pride", "lust", "envy"]

SIN_ROSTER = """
The full council of coaches, for the purpose of accurate redirects:
- Gluttony: consumption - food, alcohol, caffeine, scrolling, dopamine-seeking
- Wrath: physical discipline, channeled aggression, facing discomfort
- Pride: mastery and competence - deliberate practice, skill-building
- Lust: relationships and genuine human connection
- Envy: ambition, reframed as competing against your own past self
- Greed: wealth and stewardship - spending, saving, investing, long-term security
- Sloth: notices gaps between stated intentions and actual actions; has no topic domain of its own

Lucifer oversees the coaches themselves and is not someone to redirect the person to directly.
"""

EXTRACTION_PROMPT = """
You will be given the persona and domain of an AI coach, followed by a transcript of a conversation between the coach and a person.

Identify anything worth remembering long-term: either a slow-changing baseline fact about the person, or a specific meaningful event or commitment.

Only extract items that fall within this agent's own domain and scope of authority, as described in the persona above.
If the conversation touched on another coach's domain, do not record it here, even if it seems noteworthy - 
it belongs in that other coach's own memory, which this agent cannot write to.

Baseline is for truly stable characteristics: personality traits, values, long-term goals, and patterns you have real reason to believe are durable.
Do not record current circumstances that could plausibly change soon (e.g. a temporary habit, job status prone to change) as baseline,
log them as a dated event instead, so it's understood as a snapshot in time rather than a permanent trait.

If the conversation includes multiple distinct facts or figures (e.g. separate numbers for different budget categories), 
extract each as its own separate baseline entry rather than summarizing them into one.

A meaningful event doesn't require an action to have been completed - 
deciding to hold off on something after real consideration is just as memorable as following through on it.

If something has not happened yet, phrase it as a commitment or intention using language like "committed to," "plans to," or "wants to" -
never state a future plan as settled fact, since plans are prone to change.

Respond with ONLY valid JSON, no markdown formatting, no commentary: a list of objects, each shaped either:
{"type": "baseline", "key": "short_snake_case_key", "value": "the fact"}
or
{"type": "event", "content": "description of what happened or was committed to"}

Only include truly meaningful items, not routine details.
If nothing meaningful is found, respond with an empty list: []
"""

COACHING_PRINCIPLE = """
When the person lacks a concrete structure, plan, or method for something in your domain,
proactively offer one rather than only diagnosing the problem or applying pressure.
Equip them with something actionable, not just a verdict.
"""

# avoids a truncated/corrupted file if the process dies mid-write
def _atomic_write_json(path, data):
    path = Path(path)
    fd, temp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="UTF-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_path, path)
    except Exception:
        os.remove(temp_path)
        raise

def memory_dir(agent_name):
    return Path("memory") / agent_name

def list_available_agents():
    base = Path("memory")
    if not base.exists():
        return []
    return sorted([agent.name for agent in base.iterdir() if agent.is_dir()])

def load_memory(agent_name):
    m_dir = memory_dir(agent_name)
    
    try:
        with open(m_dir / "baseline.json", "r", encoding="UTF-8") as f:
                baseline = json.load(f)
    except FileNotFoundError:
        baseline = {}

    try:
        with open(m_dir / "events.json", "r", encoding="UTF-8") as f:
                events = json.load(f)
    except FileNotFoundError:
        events = []

    return baseline, events

def save_memory(agent_name, baseline, events):
    m_dir = memory_dir(agent_name)
    m_dir.mkdir(parents=True, exist_ok=True)

    _atomic_write_json(m_dir / "baseline.json", baseline)
    _atomic_write_json(m_dir / "events.json", events)

def setup_client():
    load_dotenv()

    API_KEY = os.getenv("GEMINI_API_KEY")
    if not API_KEY:
        print("Error: GEMINI_API_KEY not found. Check your .env file.")
        sys.exit(1)

    return genai.Client(api_key=API_KEY)

def build_system_prompt(persona_prompt, baseline, events):
    recent_events = events[-10:]
    return (
        f"{persona_prompt}\n\n"
        f"{SIN_ROSTER}\n\n"
        f"{COACHING_PRINCIPLE}\n\n"
        f"What you know about this person so far (baseline):\n"
        f"{json.dumps(baseline, indent=2)}\n\n"
        f"Recent relevant events:\n"
        f"{json.dumps(recent_events, indent=2)}"
    )

def build_extraction_prompt(persona_prompt):
    return f"{EXTRACTION_PROMPT}\n\nAgent persona and domain:\n{persona_prompt}"

def extract_memory(client, model, extraction_prompt, transcript_text):
    return call_model_text(client=client, model=model, system_instruction=extraction_prompt, input_text=transcript_text)

def parse_proposals(raw_response):
    sanitized = raw_response.strip()
    if sanitized.startswith("```"):
        sanitized = sanitized.removeprefix("```json").removeprefix("```").strip()
        sanitized = sanitized.removesuffix("```").strip()

    try:
        proposals = json.loads(sanitized)
        if not isinstance(proposals, list):
            print(f"Couldn't parse proposals as a list: {proposals}")
            return []
        return proposals
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return []

def review_and_save_memory(agent_name, proposals, baseline, events):
    if not proposals:
        print("\nNo new memory items to save.")
        return

    print(f"\nFound {len(proposals)} new memory item(s):")
    changed = False

    for p in proposals:
        p_type = p.get("type")

        if p_type == "baseline":
            key, value = p.get("key"), p.get("value")
            print(f"\n  [baseline] {key}: {value}")
            if input("  Save this? (y/n): ").strip().lower() == "y":
                baseline[key] = value
                changed = True
        elif p_type == "event":
            content = p.get("content")
            print(f"\n  [event] {content}")
            if input("  Save this? (y/n): ").strip().lower() == "y":
                events.append({"date": datetime.now().isoformat(), "content": content})
                changed = True
        else:
            print(f"\n  [unknown type, skipping] {p}")

    if changed:
        save_memory(agent_name, baseline, events)
        print("\nMemory updated.")
    else:
        print("\nNo changes made to memory.")

def save_failed_transcript(agent_name, transcript):
    fail_dir = Path("failed_extractions") / agent_name
    fail_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = fail_dir / f"{timestamp}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(transcript))
    return path

def import_agent_module(agent_name):
    try:
        return importlib.import_module(agent_name)
    except ImportError:
        return None

def call_model(client, model, system_instruction, input_text, previous_interaction_id=None, max_retries=2):
    attempt = 0
    while True:
        try:
            return client.interactions.create(
                model=model,
                input=input_text,
                system_instruction=system_instruction,
                previous_interaction_id=previous_interaction_id,
            )
        except Exception as e:
            attempt += 1
            if attempt > max_retries:
                raise
            print(f"Error: {e}")
            print(f"[Temporary error during extraction, retrying in 30s... attempt {attempt}/{max_retries}]")
            # set to 30 seconds to sidestep the RPM minute of gemini's free plan (2 retries at 30s apart will have at least the 2nd one be outside the same minute)
            time.sleep(30)

# thin wrapper to avoid boilerplate in the 99% of cases where only the output_text is needed
def call_model_text(client, model, system_instruction, input_text, max_retries=2):
    return call_model(client=client, model=model, system_instruction=system_instruction, input_text=input_text, max_retries=max_retries).output_text

def run_agent(agent_name, display_name, persona_prompt, model=DEFAULT_MODEL):
    baseline, events = load_memory(agent_name)
    client = setup_client()
    system_prompt = build_system_prompt(persona_prompt, baseline, events)

    transcript = []
    last_id = None

    print("="*50)
    print(f"{agent_name.upper()}")
    print("Type 'quit' or 'exit' to end the session.")
    print("="*50)

    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in ("quit", "exit"):
            print("Ending session.")
            break
        if not user_input:
            continue


        try:
            interaction = call_model(client=client, model=model, system_instruction=system_prompt, input_text=user_input, previous_interaction_id=last_id)
            last_id = interaction.id
            reply = interaction.output_text
            print(f"\n{display_name}: {reply}")

            transcript.append(f"You: {user_input}")
            transcript.append(f"{display_name}: {reply}")
        except Exception as e:
            print(f"Error during interaction: {e}")

    if transcript:
        print("\nReviewing session for memory extraction...")
        extraction_prompt = build_extraction_prompt(persona_prompt)
        try:
            raw = extract_memory(client, EXTRACTION_MODEL, extraction_prompt, "\n".join(transcript))
            proposals = parse_proposals(raw)
            review_and_save_memory(agent_name, proposals, baseline, events)
        except Exception as e:
            print(f"\n[Memory extraction failed: {e}]")
            saved_path = save_failed_transcript(agent_name, transcript)
            print(f"[Transcript saved to {saved_path}, nothing saved to agent memory]")
    


"""
agent_engine.py
Shared engine for a single-domain coach agent.
Handles memory, chat loop, and memory extraction.
Agent-specific files (e.g. gluttony.py) import run_agent() and input their name and persona.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from google import genai

DEFAULT_MODEL = "gemini-3.6-flash"

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
Do not record current circumstances that could plausibly change soon (e.g. a temporary habit, job status prone to change) 
as baseline log them as a dated even instead, so it's understood as a snapshot in time rather than a permanent trait.

If something has not happened yet, phrase it as a commitment or intention using language like "committed to," "plans to," or "wants to" -
never state a future plan as settled fact, since plans are prone to change.

Respond with ONLY valid JSON, no markdown formatting, no commentary: a list of objects, each shaped either:
{"type": "baseline", "key": "short_snake_case_key", "value": "the fact"}
or
{"type": "event", "content": "description of what happened or was committed to"}

Only include truly meaningful items, not routine details.
If nothing meaningful is found, respond with an empty list: []
"""

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
        with open(m_dir / "baseline.json", "r") as f:
                baseline = json.load(f)
    except FileNotFoundError:
        baseline = {}

    try:
        with open(m_dir / "events.json", "r") as f:
                events = json.load(f)
    except FileNotFoundError:
        events = []

    return baseline, events

def save_memory(agent_name, baseline, events):
    m_dir = memory_dir(agent_name)
    m_dir.mkdir(parents=True, exist_ok=True)

    with open(m_dir / "baseline.json", "w") as f:
        json.dump(baseline, f, indent=2)

    with open(m_dir / "events.json", "w") as f:
        json.dump(events, f, indent=2)

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
        f"What you know about this person so far (baseline):\n"
        f"{json.dumps(baseline, indent=2)}\n\n"
        f"Recent relevant events:\n"
        f"{json.dumps(recent_events, indent=2)}"
    )

def build_extraction_prompt(persona_prompt):
    return f"{EXTRACTION_PROMPT}\n\nAgent persona and domain:\n{persona_prompt}"

def extract_memory(client, model, extraction_prompt, transcript_text):
    interaction = client.interactions.create(
        model=model,
        input=transcript_text,
        system_instruction=extraction_prompt,
    )
    return interaction.output_text

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

def run_agent(agent_name, display_name, persona_prompt, model=DEFAULT_MODEL):
    baseline, events = load_memory(agent_name)
    client = setup_client()
    system_prompt = build_system_prompt(persona_prompt, baseline, events)

    transcript = []
    last_id = None

    print("="*50)
    print(f"{agent_name.upper()} - Phase 2 (with memory)")
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
            interaction = client.interactions.create(
                model=model,
                input=user_input,
                system_instruction=system_prompt,
                previous_interaction_id=last_id,
            )
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
        raw = extract_memory(client, model, extraction_prompt, "\n".join(transcript))
        proposals = parse_proposals(raw)
        review_and_save_memory(agent_name, proposals, baseline, events)
    


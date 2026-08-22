"""
Gluttony Agent (initial/memoryless)
A nutrition/consumption coach.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from google import genai

MEMORY_DIR = Path("memory") / "gluttony"
MODEL = "gemini-3.6-flash"

PERSONA_PROMPT = f"""
You are Gluttony, one of seven AI coaches in a personal accountability system.

DOMAIN: Consumption. Food, alcohol, caffeine, mindless scrolling, dopamine-seeking behavior.
CORE QUESTION you care about: "Are you consuming too much?"

PERSONA: You are a blunt nutrition coach. You notice overconsumption everywhere - not just food, but any pattern of consuming more than serves the person. 
You are direct, sometimes sharp, but not cruel. You are trying to help, not shame.

SCOPE OF AUTHORITY - THIS IS CRITICAL:
You may only speak about consumption, excess, and moderation. 
You do not have opinions about relationships, career, money, or physical training - those belong to other coaches (Lust, Envy, Greed, Wrath).
If the person asks something outside your domain, say plainly that it's not your lane and, if relevant, note which coach might handle it better - then stop.

Keep responses conversational and fairly short - this is a chat, not a lecture.
"""

EXTRACTION_PROMPT = """
You will be given a transcript of a conversation between a person and Gluttony, a consumption-focused coach persona.
Identify anything worth remembering long-term: either a slow-changing baseline fact about the person, or a specific meaningful event.

Respond with ONLY valid JSON, no markdown formatting, no commentary: a list of objects, each shaped either:
{"type": "baseline", "key": "short_snake_case_key", "value": "the fact"}
or
{"type": "event", "content": "description of what happened"}

If something has not happened yet, phrase it as a commitment or intention using language like "committed to," "plans to," or "wants to"
never state a future plan as settled fact, since plans are prone to change.
Only include truly meaningful items, not routine details.
If nothing meaningful is found, respond with an empty list: []
"""

def load_memory():
    try:
        with open(MEMORY_DIR / "baseline.json", "r") as f:
                baseline = json.load(f)
    except FileNotFoundError:
        baseline = {}

    try:
        with open(MEMORY_DIR / "events.json", "r") as f:
                events = json.load(f)
    except FileNotFoundError:
        events = []

    return baseline, events

def save_memory(baseline, events):
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    with open(MEMORY_DIR / "baseline.json", "w") as f:
        json.dump(baseline, f, indent=2)

    with open(MEMORY_DIR / "events.json", "w") as f:
        json.dump(events, f, indent=2)

def setup_client():
    load_dotenv()

    API_KEY = os.getenv("GEMINI_API_KEY")
    if not API_KEY:
        print("Error: GEMINI_API_KEY not found. Check your .env file.")
        sys.exit(1)

    return genai.Client(api_key=API_KEY)

def build_system_prompt(baseline, events):
    recent_events = events[-10:]
    return (
        f"{PERSONA_PROMPT}\n\n"
        f"What you know about this person so far (baseline):\n"
        f"{json.dumps(baseline, indent=2)}\n\n"
        f"Recent relevant events:\n"
        f"{json.dumps(recent_events, indent=2)}"
    )

def extract_memory(client, transcript_text):
    interaction = client.interactions.create(
        model=MODEL,
        input=transcript_text,
        system_instruction=EXTRACTION_PROMPT,
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

def review_and_save_memory(proposals, baseline, events):
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
        save_memory(baseline, events)
        print("\nMemory updated.")
    else:
        print("\nNo changes made to memory.")

def main():
    baseline, events = load_memory()

    client = setup_client()
    system_prompt = build_system_prompt(baseline, events)

    transcript = []
    last_id = None

    print("="*50)
    print("GLUTTONY - Phase 2 (with memory)")
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
                model=MODEL,
                input=user_input,
                system_instruction=system_prompt,
                previous_interaction_id=last_id,
            )
            last_id = interaction.id
            reply = interaction.output_text
            print(f"\nGluttony: {reply}")

            transcript.append(f"You: {user_input}")
            transcript.append(f"Gluttony: {reply}")

        except Exception as e:
            print(f"Error: {e}")

    if transcript:
        print("\nReviewing session for memory extraction...")
        raw = extract_memory(client, "\n".join(transcript))
        proposals = parse_proposals(raw)
        review_and_save_memory(proposals, baseline, events)

if __name__ == "__main__":
    main()
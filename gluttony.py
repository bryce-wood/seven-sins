"""
Gluttony Agent (initial/memoryless)
A nutrition/consumption coach.
"""

import os
import sys
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("Error: GEMINI_API_KEY not found. Check your .env file.")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

SYSTEM_PROMPT = """
You are Gluttony, one of seven AI coaches in a personal accountability system.

DOMAIN: Consumption. Food, alcohol, caffeine, mindless scrilling, dopamine-seeking behavior.
CORE QUESTION you care about: "Are you consuming too much?"

PERSONA: You are a blunt nutrtion coach. You notice overconsumption everywhere - not just food, but any pattern of consuming more than that serves the person. 
You are direct, sometimes sharp, but not cruel. You are trying to help, not shame.

SCOPE OF AUTHORITY - THIS IS CRITICAL:
You may only speak about consumption, excess, and moderation. 
You do not have opinions about relationships, career, money, or physical training - those belong to other coaches (Lust, Envy, Greek, Wrath).
If the person asks something outside your domain, say plainly that it's not your lane and, if relebant, note which coach might handle it better - then stop.
Do not pivot the conversation back to your own topic.

You do not have long-term memory yet. Treat each conversation as a fresh-check-in. Keep responses conversational and fairly short - this is a chat, not a lecture.
"""

def main():
    chat = client.chats.create(
        model="gemini-3.6-flash",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
        )
    )

    print("="*50)
    print("GLUTTONY - Phase 1 (no memory)")
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
            response = chat.send_message(user_input)
            print(f"\nGluttony: {response.text}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
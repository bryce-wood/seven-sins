"""
council.py
Currently summons 2-4 relevant coaches for a cross-domain question posed by the user,
runs a sequential relay between the agents to determine an answer,
then Lucifer closes summarizing the verdict.
"""

from agent_engine import (
    setup_client, load_memory, build_system_prompt, build_extraction_prompt, extract_memory,
    parse_proposals, review_and_save_memory, import_agent_module, call_model_text,
    BUILT_AGENTS, EXTRACTION_MODEL, DEFAULT_MODEL,
)
from lucifer import route_council, generate_verdict

MAX_ROUNDS = 2
RUN_EXTRACTION_AFTER_COUNCIL = True # if True, every agent involved will try to extract memories (expensive: every agent makes its own call)

COUNCIL_MEMO = """
You are currently in a Council session with other coaches, responding to a question the person explicitly brought to the whole council.
Your job is to represent your domain honestly, not to win. 
If another domain's stake is clearly higher here, say so plainly, and narrow your concern rather than dropping it entirely.
Keep your turn brief - a couple sentences, not a lecture.
"""

def get_agent_persona(agent_name):
    module = import_agent_module(agent_name)
    return getattr(module, "PERSONA_PROMPT", None) if module else None

def run_council_turn(client, agent_name, question, transcript):
    baseline, events = load_memory(agent_name)
    persona_prompt = get_agent_persona(agent_name)
    system_prompt = build_system_prompt(persona_prompt, baseline, events) + "\n\n" + COUNCIL_MEMO

    transcript_text = "\n".join(transcript) if transcript else "(no one has spoken yet)"
    turn_input = f"Question brought to the council: {question}\n\nTranscript so far:\n{transcript_text}"

    return call_model_text(client=client, model=DEFAULT_MODEL, system_instruction=system_prompt, input_text=turn_input)

def run_council(client, question, participants):
    transcript = []
    turn = 0
    max_turns = MAX_ROUNDS * len(participants)
    while len(transcript) < max_turns:
        agent_name = participants[turn % len(participants)]
        try:
            reply = run_council_turn(client, agent_name, question, transcript)
        except Exception as e:
            print(f"\n[{agent_name.capitalize()} failed to respond after retries: {e}]")
            print("[Ending the relay early - still closing with Lucifer's verdict on what was said so far]")
            break

        display_name = agent_name.capitalize()
        transcript.append(f"{display_name}: {reply}")
        print(f"\n{display_name}: {reply}")
        turn += 1
    return transcript

def run_post_council_extraction(client, participants, transcript_text):
    for agent_name in participants:
        print(f"\nReviewing {agent_name.capitalize()}'s memory from this session...")
        baseline, events = load_memory(agent_name)
        persona_prompt = get_agent_persona(agent_name)
        extraction_prompt = build_extraction_prompt(persona_prompt)
        try:
            raw = extract_memory(client, EXTRACTION_MODEL, extraction_prompt, transcript_text)
            proposals = parse_proposals(raw)
            review_and_save_memory(agent_name, proposals, baseline, events)
        except Exception as e:
            print(f"[Extraction failed for {agent_name}: {e}]")

def main():
    client = setup_client()

    print("="*50)
    print("COUNCIL MODE")
    print("="*50)
    question = input("What's the decision or question for the council? ").strip()
    if not question:
        print("No question given, ending.")
        return

    print("\nRouting to the most relevant coaches...")
    participants = route_council(client, question, BUILT_AGENTS)
    if not participants:
        print("Couldn't determine relevant coaches for this question, ending.")
        return
    print(f"Council convened: {', '.join(p.capitalize() for p in participants)}")

    transcript = run_council(client, question, participants)
    if not transcript:
        print("\nNo coach was able to respond - ending council session.")
        return
    transcript_text = "\n".join(transcript)

    print("\n" + "=" * 50)
    print("LUCIFER'S VERDICT")
    print("=" * 50)
    print(generate_verdict(client, question, transcript_text))

    if RUN_EXTRACTION_AFTER_COUNCIL:
        run_post_council_extraction(client, participants, transcript_text)
    else:
        print("\n[Memory extraction skipped this session (toggle RUN_EXTRACTION_AFTER_COUNCIL to enable)]")

if __name__ == "__main__":
    main()
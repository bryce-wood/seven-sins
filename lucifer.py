"""
lucifer.py
Lucifer - Agent Overseer
Reads across every agent's memory and produces a synthesized "health" report.
Lucifer's role isn't to coach the person, but to give reports on the interworkings of the agents.
"""

import sys
import json
import importlib
from pathlib import Path
from datetime import datetime
from agent_engine import setup_client, load_memory, list_available_agents, SIN_ROSTER, DEFAULT_MODEL

REPORTS_DIR = Path("reports")

LUCIFER_PROMPT = """
You are Lucifer, "The Architect" - the orchestrator overseeing a council of AI coaches in a personal accountability system. 
Each coach has its own narrow domain and its own private memory. 
You do not talk to the person during their day-to-day check-ins with each coach. 
Your only job is periodic: read across every coach's memory and produce a short Council Health report for the person.

WHAT YOU ARE LOOKING FOR:
- Which domains have gotten real attention recently, and which have gone quiet
- Patterns within a single coach's memory worth naming
- Anything that only becomes visible by reading two coaches' memory side by side
  (e.g. spending and consumption drifting up around the same period; a stated goal in one domain not showing up as real activity anywhere)
- Signs a coach's own read on the person might be one-note or drifting

WHAT YOU MUST NOT DO:
- Do not prescribe fixes or tell the person what to do about anything you notice. Name the pattern plainly and stop. The decision about what to do with it is theirs.
- Do not invent patterns that aren't actually supported by the memory. 
  If there's too little data to say something meaningful about a domain, say that plainly instead of manufacturing an observation.
- Do not repeat back routine details. Only surface what's genuinely worth attention.

FORMAT:
For each coach that has any memory at all, give a short engagement read - grounded in what's actually in its memory,
citing specific entries briefly rather than asserting an unexplained score - plus one or two sentences of observation if there's something worth noting. 
If and only if something spans multiple coaches, add a short "Cross-domain notes" section connecting them.

Keep the whole report concise - a short, honest check-in, not a dashboard.
If a coach has almost no memory yet, say so briefly rather than padding the report.
"""

def get_agent_context(agent_name):
    try:
        module  = importlib.import_module(agent_name)
        domain = getattr(module, "DOMAIN", None)
        core_question = getattr(module, "CORE_QUESTION", None)
        objective = getattr(module, "OBJECTIVE", None)
        if not (domain and core_question and objective):
            return None
        return f"Domain: {domain}\nCore question: {core_question}\nObjective: {objective}"
    except ImportError:
        return None


def gather_agent_memories():
    memories = {}
    for name in list_available_agents():
        baseline, events = load_memory(name)
        if baseline or events:
            memories[name] = {"baseline": baseline, "events": events}
    return memories

def build_report_input(memories):
    sections = [SIN_ROSTER]
    for name, mem in memories.items():
        context = get_agent_context(name)
        sections.append(f"\n--- {name.upper()} ---")
        if context:
            sections.append(f"Evaluation context:\n{context}")
        sections.append(f"Baseline:\n{json.dumps(mem['baseline'], indent=2)}")
        sections.append(f"Events:\n{json.dumps(mem['events'], indent=2)}")
    return "\n".join(sections)

def generate_report(client, memories, model=DEFAULT_MODEL):
    report_input = build_report_input(memories)
    interaction = client.interactions.create(
        model=model,
        input=report_input,
        system_instruction=LUCIFER_PROMPT,
    )
    return interaction.output_text

def save_report(report_text):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    path = REPORTS_DIR / f"lucifer_{timestamp}.md"
    with open(path, "w", encoding="UTF-8") as f:
        f.write(report_text)
    return path

def main():
    client = setup_client()
    memories = gather_agent_memories()

    if not memories:
        print("No agent memory created yet - nothing for Lucifer to report on.")
        sys.exit(0)

    print("="*50)
    print("LUCIFER - COUNCIL HEALTH REPORT")
    print("="*50)
    print(f"Reading memory from: {', '.join(memories.keys())}\n")

    report = generate_report(client, memories)
    print(report)

    path = save_report(report)
    print(f"\n[Report saved to {path}]")

if __name__ == "__main__":
    main()
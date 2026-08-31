"""
lucifer.py
Lucifer - Agent Overseer
Reads across every agent's memory and produces a synthesized "health" report.
Lucifer's role isn't to coach the person, but to give reports on the interworkings of the agents.
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from agent_engine import setup_client, load_memory, list_available_agents, import_agent_module, call_model_text, SIN_ROSTER, DEFAULT_MODEL

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

ROUTER_PROMPT = """
You are Lucifer, "The Architect," acting as router for a council session. 
You will be given the roster of coaches with their domain and objective, followed by a question or decision the person wants the council to weigh in on.

Pick the 2 to 4 coaches most relevant to this question, ranked from most to least relevant. 
Only include a coach if it has a genuine stake in this specific question - most questions only concern one to three domains, so do not pad the list just to reach four.

Respond with ONLY valid JSON, no markdown formatting, no commentary:
a list of agent names in ranked order, e.g. ["greed", "envy"]
"""

COUNCIL_VERDICT_PROMPT = """
You are Lucifer, "The Architect," closing out a council session. 
You will be given the original question and the full relay transcript of the coaches who weighed in.

Report honestly on the outcome: say plainly whether the coaches actually converged on something,
or whether there's a genuine unresolved tension between them - and if so, name that tension clearly. 
Do not prescribe what the person should do. The decision is theirs; your job is only to characterize what was actually said.

Keep it short - a few sentences, not a report.
"""


def get_agent_context(agent_name):
    module = import_agent_module(agent_name)
    if module is None:
        return None
    domain = getattr(module, "DOMAIN", None)
    core_question = getattr(module, "CORE_QUESTION", None)
    objective = getattr(module, "OBJECTIVE", None)
    if not (domain and core_question and objective):
        return None
    return f"Domain: {domain}\nCore question: {core_question}\nObjective: {objective}"

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
    return call_model_text(client=client, model=model, system_instruction=LUCIFER_PROMPT, input_text=report_input)

def save_report(report_text):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    path = REPORTS_DIR / f"lucifer_{timestamp}.md"
    with open(path, "w", encoding="UTF-8") as f:
        f.write(report_text)
    return path

# for Lucifer's role in the council
# given Lucifer's response of relevant agents, parses the message to determine the agents
def parse_agent_list(raw_response, valid_names):
    sanitized = raw_response.strip()
    if sanitized.startswith("```"):
        sanitized = sanitized.removeprefix("```json").removeprefix("```").strip()
        sanitized = sanitized.removesuffix("```").strip()
    try:
        names = json.loads(sanitized)
        if not isinstance(names, list):
            print(f"Router response wasn't a list: {names}")
            return []
    except json.JSONDecodeError as e:
        print(f"Error parsing router response: {e}")
        return []

    valid = [n for n in names if n in valid_names]
    if len(valid) < len(names):
        print(f"[Router named unknown agent(s), ignoring: {set(names) - set(valid)}]")
    return valid

# for Lucifer's role in the council
# gives Lucifer the question for the council and agents to choose from as well as their "context" (domain, core question, and objective from agent prompt)
# Lucifer then decides which agents are relevant to weigh in on the Council topic (question)
def route_council(client, question, agent_names, model=DEFAULT_MODEL):
    contexts = []
    for name in agent_names:
        context = get_agent_context(name)
        if context:
            contexts.append(f"--- {name} ---\n{context}")

    router_input = f"{SIN_ROSTER}\n\n" + "\n\n".join(contexts) + f"\n\nQuestion: {question}"
    raw = call_model_text(client=client, model=model, system_instruction=ROUTER_PROMPT, input_text=router_input)
    return parse_agent_list(raw, agent_names)

# for Lucifer's role in the council
# final call to Lucifer to determine the conclusion of the Council (or where they got stuck)
def generate_verdict(client, question, transcript_text, model=DEFAULT_MODEL):
    verdict_input = f"Question: {question}\n\nCouncil transcript:\n{transcript_text}"
    return call_model_text(client=client, model=model, system_instruction=COUNCIL_VERDICT_PROMPT, input_text=verdict_input)

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
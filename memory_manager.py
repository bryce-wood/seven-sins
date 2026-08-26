"""
memory_manager.py
View and delete baseline/event entries for any agent's memory
Usage: python memory_manager.py [agent_name]
If no agent name is given, instead lists available agents to choose from
"""

import sys
from agent_engine import load_memory, save_memory, list_available_agents

def choose_agent():
    agents = list_available_agents()
    if not agents:
        print("No agent memory found.")
        sys.exit(1)

    print("Available agents:")
    for i, name in enumerate(agents, start=1):
        print(f"  {i}. {name}")

    choice = input("Choose an agent (number or name): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(agents):
        return agents[int(choice)-1]
    if choice in agents:
        return choice

    print("Not a valid choice.")
    sys.exit(1)

def parse_indices(raw, max_index):
    if not raw.strip():
        return set()

    indices = set()
    for raw_num in raw.split(","):
        raw_num = raw_num.strip()
        if raw_num.isdigit():
            num = int(raw_num)
            # if num is in range 1 -> n
            if 1 <= num <= max_index:
                indices.add(num-1)
    return indices

def review_baseline(baseline):
    if not baseline:
        print("\nBaseline is empty.")
        return baseline, False

    keys = list(baseline.keys())
    print("\nBaseline entries:")
    for i, key in enumerate(keys, start=1):
        print(f"  {i}. {key}: {baseline[key]}")

    raw = input("\nEnter numbers to delete (comma-separated), or press Enter to skip: ")
    to_delete = parse_indices(raw, len(keys))

    if not to_delete:
        return baseline, False

    # reversed so the array shifting doesn't impact deletion
    # e.g. 123 remove at pos 0 = 23 remove at pos 1 = 2 vs 123 remove at pos 1 = 13 remove at pos 0 = 3, which is expected
    for i in sorted(to_delete, reverse=True):
        removed_key = keys[i]
        print(f"  Deleted: {removed_key}")
        del baseline[removed_key]

    return baseline, True

def review_events(events):
    
    if not events:
        print("\nEvents log is empty.")
        return events, False

    print("\nEvent entries:")
    for i, event in enumerate(events, start=1):
        date = event.get("date", "unknown date")
        content = event.get("content", "")
        print(f"  {i}. [{date}] {content}")

    raw = input("\nEnter numbers to delete (comma-separated), or press Enter to skip: ")
    to_delete = parse_indices(raw, len(events))

    if not to_delete:
        return events, False

    # reversed so the array shifting doesn't impact deletion
    # e.g. 123 remove at pos 0 = 23 remove at pos 1 = 2 vs 123 remove at pos 1 = 13 remove at pos 0 = 3, which is expected
    for i in sorted(to_delete, reverse=True):
        removed = events.pop(i)
        print(f"  Deleted: [{removed.get('date', 'unknown date')}] {removed.get('content', '')}")

    return events, True

def main():
    # either passed on call or go to picker
    agent_name = sys.argv[1] if len(sys.argv) > 1 else choose_agent()
    baseline, events = load_memory(agent_name)

    print("="*50)
    print(f"MEMORY MANAGER - {agent_name.upper()}")
    print("="*50)

    baseline, baseline_changed = review_baseline(baseline)
    events, events_changed = review_events(events)

    if baseline_changed or events_changed:
        save_memory(agent_name, baseline, events)
        print("\nChanges saved.")
    else:
        print("\nNo changes made.")

if __name__ == "__main__":
    main()
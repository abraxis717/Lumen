from lumen_core.kernel.event import Event

def execute(event: Event) -> str:
    if event.result == "ALLOW" and event.state != "FORBIDDEN":
        return f"EXECUTED: {event.proposal}"
    return "BLOCKED"

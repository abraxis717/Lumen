from lumen_core.kernel.event import Event


def execute(event: Event) -> str:
    """
    Executes an event according to its result and Soohak caveat.

    ALLOW  + log message  →  log message (Soohak refusal caveat)
    ALLOW  + no log       →  EXECUTED: <proposal>
    BLOCK                        →  BLOCKED
    """
    if event.result == "ALLOW" and event.state != "FORBIDDEN":
        if event.log:
            return event.log
        return f"EXECUTED: {event.proposal}"
    return "BLOCKED"

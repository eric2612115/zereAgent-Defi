# src/custom_actions/phase_tools.py

import logging
from src.action_handler import register_action

logger = logging.getLogger("custom_actions.phase_tools")


@register_action("think_and_plan")
def think_and_plan(agent, **kwargs):
    """
    Structured thinking tool to analyze user requests and plan response strategies.
    This should be the first tool called when handling any user query.
    """
    user_request = kwargs.get("user_request", "")
    main_phase = kwargs.get("main_phase", 1)
    main_phase_content = kwargs.get("main_phase_content", "Understanding Request")
    sub_phase = kwargs.get("sub_phase", 1)
    sub_phase_content = kwargs.get("sub_phase_content", "Identifying explicit request type")

    # Store the current phase in agent state
    if not hasattr(agent, 'state'):
        agent.state = {}

    agent.state["current_main_phase"] = main_phase
    agent.state["current_main_phase_content"] = main_phase_content
    agent.state["current_sub_phase"] = sub_phase
    agent.state["current_sub_phase_content"] = sub_phase_content

    # Log the thinking process (for debugging, but also helps keep track in the agent's output)
    thinking_log = f"""
MAIN PHASE {main_phase}: {main_phase_content}
SUB-PHASE {sub_phase}: {sub_phase_content}

Analyzing user request: "{user_request}"

I'll think through this systematically:
1. What is the user explicitly asking for?
2. What information is missing that I might need?
3. What tools would be appropriate for this request?
4. What should be my plan of action?
"""

    # Return the thinking log
    return thinking_log


@register_action("phase_transition")
def phase_transition(agent, **kwargs):
    """
    Mark completion of current phase and transition to next phase.
    Track reasoning through phases structurally.
    """
    current_main_phase = kwargs.get("current_main_phase", 1)
    current_main_phase_content = kwargs.get("current_main_phase_content", "")
    current_sub_phase = kwargs.get("current_sub_phase", 1)
    current_sub_phase_content = kwargs.get("current_sub_phase_content", "")

    next_main_phase = kwargs.get("next_main_phase", current_main_phase)
    next_main_phase_content = kwargs.get("next_main_phase_content", "")
    next_sub_phase = kwargs.get("next_sub_phase", current_sub_phase + 1)
    next_sub_phase_content = kwargs.get("next_sub_phase_content", "")

    transition_reason = kwargs.get("transition_reason", "Moving to next phase")

    # Update agent state with new phase
    if not hasattr(agent, 'state'):
        agent.state = {}

    agent.state["current_main_phase"] = next_main_phase
    agent.state["current_main_phase_content"] = next_main_phase_content
    agent.state["current_sub_phase"] = next_sub_phase
    agent.state["current_sub_phase_content"] = next_sub_phase_content

    # Format the transition log
    transition_log = f"""
COMPLETING: PHASE {current_main_phase}.{current_sub_phase} - {current_main_phase_content}: {current_sub_phase_content}

REASON FOR TRANSITION: {transition_reason}

MOVING TO: PHASE {next_main_phase}.{next_sub_phase} - {next_main_phase_content}: {next_sub_phase_content}
"""

    return transition_log


@register_action("reflect_on_error")
def reflect_on_error(agent, **kwargs):
    """
    When an error is encountered, use this tool to reflect and adjust approach.
    Helps AI learn from errors and improve handling.
    """
    error_message = kwargs.get("error_message", "Unknown error")
    previous_approach = kwargs.get("previous_approach", "")
    main_phase = kwargs.get("main_phase", 3)
    main_phase_content = kwargs.get("main_phase_content", "Verifying Method")
    sub_phase = kwargs.get("sub_phase", 1)
    sub_phase_content = kwargs.get("sub_phase_content", "Self-checking plan optimization")

    # Store the current phase in agent state
    if not hasattr(agent, 'state'):
        agent.state = {}

    agent.state["current_main_phase"] = main_phase
    agent.state["current_main_phase_content"] = main_phase_content
    agent.state["current_sub_phase"] = sub_phase
    agent.state["current_sub_phase_content"] = sub_phase_content

    # Generate reflection on the error
    reflection = f"""
ERROR REFLECTION (PHASE {main_phase}.{sub_phase} - {main_phase_content}: {sub_phase_content})

ERROR MESSAGE: {error_message}

PREVIOUS APPROACH: {previous_approach}

REFLECTION:
1. Why did this approach fail?
   - The approach might have failed because of: [analyzing reasons]

2. What would be a better approach?
   - A better approach might be: [suggesting alternatives]

3. How can I avoid this error in the future?
   - To avoid this in the future: [preventative measures]

ADJUSTED PLAN:
[New approach based on reflection]
"""

    return reflection
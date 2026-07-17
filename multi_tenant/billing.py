"""Token cost calculation."""

import math


def calculate_cost(workflow_body: dict, user: dict | None = None) -> int:
    """Calculate the token cost for a workflow execution.

    Walks through the workflow nodes to estimate cost based on parameters.
    Falls back to flat fee when no cost-related parameters found.
    """
    prompt = workflow_body.get("prompt", workflow_body)
    cost = 10  # minimum base cost

    if not isinstance(prompt, dict):
        return cost

    # Walk all nodes looking for cost-related parameters
    found_steps = False
    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        class_type = node.get("class_type", "")

        # Count steps (typically from KSampler nodes)
        if "steps" in inputs and isinstance(inputs["steps"], (int, float)):
            step_cost = int(inputs["steps"]) * 1  # 1 token per step
            cost += step_cost
            found_steps = True

        # Count megapixels from image dimensions
        if "width" in inputs and "height" in inputs:
            w = float(inputs.get("width", 512))
            h = float(inputs.get("height", 512))
            mp = (w * h) / (1024 * 1024)
            cost += math.ceil(mp * 5)  # 5 tokens per megapixel

        # Batch size multiplier
        if "batch_size" in inputs and isinstance(inputs["batch_size"], (int, float)):
            batch = int(inputs["batch_size"])
            if batch > 1:
                cost *= batch

    if not found_steps:
        cost = 10  # flat fee for unknown workflows

    return max(cost, 1)

"""
Agent module for creating agents that can process inputs, use tools, and hand off to other agents.
"""

import os
import json
import openai
from tool import execute_tool
from dotenv import load_dotenv
from typing import List, Optional, Dict


load_dotenv()

client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_API_BASE_URL"),
)


class Agent:
    """
    An agent that can perform tasks based on instructions and use tools or hand off to other agents.

    Agents can process inputs according to their instructions, use tools to perform
    actions, or hand off to other specialized agents when appropriate.
    """

    def __init__(
        self,
        name: str,
        description: str,
        instructions: str,
        tools: Optional[List[Dict[str, str]]] = None,
        handoffs: Optional[List["Agent"]] = None,
        model: str = "gpt-4o-mini",
    ):
        """
        Initialize an Agent instance.

        Args:
            name: The name of the agent. Should be unique, lowercase, and without spaces.
            instructions: Instructions that define the agent's behavior.
            tools: Optional list of tools the agent can use.
            handoffs: Optional list of agents this agent can hand off to.
            model: OpenAI model to use for this agent
        """
        self.name = name
        self.description = description
        self.instructions = instructions
        self.tools = tools or []
        self.handoffs = handoffs or []
        self.model = model
        self.history = []

    def __repr__(self) -> str:
        """Return string representation of the Agent."""
        return f"Agent(name='{self.name}')"

    def get_available_tools(self) -> List[Dict[str, str]]:
        """Return the list of tools available to this agent."""
        return self.tools

    def get_available_handoffs(self) -> List["Agent"]:
        """Return the list of agents this agent can hand off to."""
        return self.handoffs

    def process(self, input_text: str) -> Dict:
        """
        Process the input using OpenAI API and return the agent's response.

        Args:
            input_text: The text input to process

        Returns:
            Dict containing the agent's response and any actions taken
        """
        messages = self._prepare_messages(input_text)

        # Add handoff agents as tools
        for agent in self.handoffs:
            self.tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": f"handoff_to_{agent.name}",
                        "description": f"Hand off the conversation to the {agent.name} agent. The agent is specialized in {agent.description}.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            )

        # Call OpenAI API
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self.tools if self.tools else None,
        )

        response_message = response.choices[0].message
        self.history.append({"role": "user", "content": input_text})
        self.history.append(
            {"role": "assistant", "content": response_message.content or ""}
        )

        result = {
            "content": response_message.content,
            "tool_calls": None,
            "handoff": None,
        }

        # Handle tool calls
        if hasattr(response_message, "tool_calls") and response_message.tool_calls:
            result["tool_calls"] = []
            for tool_call in response_message.tool_calls:
                tool_name = tool_call.function.name

                # Check if this is a handoff
                if tool_name.startswith("handoff_to_"):
                    target_agent_name = tool_name[len("handoff_to_") :]
                    for agent in self.handoffs:
                        if agent.name == target_agent_name:
                            result["handoff"] = agent
                            break
                else:
                    # Execute the tool
                    for tool in self.tools:
                        if tool.name == tool_name:
                            args = json.loads(tool_call.function.arguments)
                            tool_result = execute_tool(tool_name, args)
                            result["tool_calls"].append(
                                {"tool": tool_name, "args": args, "result": tool_result}
                            )
                            break

        return result

    def _prepare_messages(self, input_text: str) -> List[Dict]:
        """Prepare the message history for the API call."""
        # Start with system instructions
        messages = [{"role": "system", "content": self.instructions}]
        # Add conversation history
        messages.extend(self.history)
        # Add the current input
        messages.append({"role": "user", "content": input_text})

        return messages

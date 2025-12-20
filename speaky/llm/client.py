"""LangChain-based LLM Client with MCP tool support."""

import logging
import os
from typing import Optional, AsyncIterator

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from .prompts import AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class LLMClient:
    """LangChain-based LLM client with MCP tool support (OpenAI compatible)."""

    def __init__(self, config: dict):
        """Initialize LLM client.

        Args:
            config: LLM configuration dict containing OpenAI settings
        """
        self.config = config
        self._llm = None
        self._tools = []
        self._agent = None
        self._initialized = False

    def _create_llm(self):
        """Create LLM instance based on configuration."""
        openai_config = self.config.get("openai", {})
        base_url = openai_config.get("base_url", "").strip()
        if not base_url:
            base_url = "https://api.openai.com/v1"
        return ChatOpenAI(
            model=openai_config.get("model", "gpt-4o-mini"),
            api_key=openai_config.get("api_key"),
            base_url=base_url,
            temperature=0.7,
        )

    async def initialize(self, mcp_servers: dict):
        """Initialize the agent with MCP tools.

        Args:
            mcp_servers: MCP server configuration dict
        """
        if self._initialized:
            return

        # Step 1: Create LLM instance
        logger.info("[LLM Client] Creating LLM instance...")
        self._llm = self._create_llm()
        logger.info(f"[LLM Client] LLM created: {self.config.get('openai', {}).get('model', 'gpt-4o-mini')}")

        # Step 2: Load MCP tools from all configured servers
        logger.info("[LLM Client] Loading MCP tools from servers...")
        self._tools = await self._load_mcp_tools(mcp_servers)
        logger.info(f"[LLM Client] Loaded {len(self._tools)} MCP tools total")

        # Step 3: Create agent and bind tools
        if self._tools:
            logger.info("[LLM Client] Creating LangGraph agent with tools...")
            self._agent = create_react_agent(
                self._llm,
                self._tools,
                prompt=AGENT_SYSTEM_PROMPT,
            )
            logger.info("[LLM Client] Agent created with MCP tools bound")
        else:
            # No tools available, use simple chain
            self._agent = None
            logger.warning("[LLM Client] No MCP tools loaded, agent will work in chat-only mode")

        self._initialized = True
        logger.info("[LLM Client] Initialization complete")

    async def _load_mcp_tools(self, mcp_servers: dict) -> list:
        """Load tools from MCP servers.

        Args:
            mcp_servers: MCP server configuration

        Returns:
            List of LangChain tools
        """
        tools = []

        enabled_servers = [name for name, cfg in mcp_servers.items() if cfg.get("enabled", False)]
        logger.info(f"[LLM Client] Enabled MCP servers: {enabled_servers}")

        for name, server_config in mcp_servers.items():
            if not server_config.get("enabled", False):
                continue

            try:
                # Try to load MCP tools using langchain-mcp-adapters
                from langchain_mcp_adapters.tools import load_mcp_tools

                # Expand ~ in command and args
                command = os.path.expanduser(server_config["command"])
                args = [os.path.expanduser(arg) for arg in server_config.get("args", [])]

                logger.info(f"[LLM Client] Connecting to MCP server '{name}': {command} {' '.join(args)}")

                # Create connection dict for StdioConnection
                connection = {
                    "transport": "stdio",
                    "command": command,
                    "args": args,
                }
                # Merge custom env with current environment
                if server_config.get("env"):
                    env = os.environ.copy()
                    env.update(server_config["env"])
                    connection["env"] = env
                    logger.info(f"[LLM Client] Custom env for '{name}': {server_config['env']}")

                server_tools = await load_mcp_tools(
                    session=None,
                    connection=connection,
                    server_name=name,
                )
                tools.extend(server_tools)
                tool_names = [t.name for t in server_tools]
                logger.info(f"[LLM Client] Loaded {len(server_tools)} tools from '{name}': {tool_names}")

            except ImportError:
                logger.warning("[LLM Client] langchain-mcp-adapters not installed, skipping MCP tools")
                break
            except Exception as e:
                logger.error(f"[LLM Client] Failed to load MCP tools from {name}: {e}")

        return tools

    async def chat(self, user_message: str) -> str:
        """Send a message and get response.

        Args:
            user_message: User's input message

        Returns:
            Agent's response string
        """
        if not self._initialized:
            raise RuntimeError("LLM Client not initialized. Call initialize() first.")

        if self._agent:
            result = await self._agent.ainvoke({
                "messages": [HumanMessage(content=user_message)],
            })
            # Extract the last AI message
            messages = result.get("messages", [])
            for msg in reversed(messages):
                if hasattr(msg, "content") and msg.content:
                    return msg.content
            return ""
        else:
            # Fallback to simple chat
            messages = [
                SystemMessage(content=AGENT_SYSTEM_PROMPT),
                HumanMessage(content=user_message),
            ]
            response = await self._llm.ainvoke(messages)
            return response.content

    async def chat_stream(self, user_message: str) -> AsyncIterator[dict]:
        """Stream chat with events for real-time UI updates.

        Args:
            user_message: User's input message

        Yields:
            Event dicts with type and data
        """
        if not self._initialized:
            raise RuntimeError("LLM Client not initialized. Call initialize() first.")

        if not self._agent:
            # Fallback to simple streaming
            messages = [
                SystemMessage(content=AGENT_SYSTEM_PROMPT),
                HumanMessage(content=user_message),
            ]
            async for chunk in self._llm.astream(messages):
                yield {
                    "type": "token",
                    "content": chunk.content,
                }
            return

        # Use astream_events for detailed event tracking
        async for event in self._agent.astream_events(
            {"messages": [HumanMessage(content=user_message)]},
            version="v2",
        ):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    yield {
                        "type": "token",
                        "content": content,
                    }

            elif kind == "on_tool_start":
                yield {
                    "type": "tool_start",
                    "name": event["name"],
                    "input": event["data"].get("input", {}),
                }

            elif kind == "on_tool_end":
                yield {
                    "type": "tool_end",
                    "name": event["name"],
                    "output": str(event["data"].get("output", ""))[:100],
                }

            elif kind == "on_tool_error":
                yield {
                    "type": "tool_error",
                    "name": event["name"],
                    "error": str(event["data"].get("error", "")),
                }

    def get_tool_names(self) -> list[str]:
        """Get list of available tool names."""
        return [tool.name for tool in self._tools]

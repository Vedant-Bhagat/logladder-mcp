"""MCP server `loglad`: wires Janhavi's registries into FastMCP (contract: contracts/interfaces.py)."""
from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts.base import Prompt, PromptArgument
from mcp.server.fastmcp.resources import FunctionResource

from loglad_mcp.config import load_settings
from loglad_mcp.core.db import SereneDb

log = logging.getLogger("loglad")


def _registries() -> tuple[list, list, list, object | None]:
    """Janhavi's modules; empty until they land so Claude Code can already connect."""
    found = []
    for mod, name in (("loglad_mcp.tools.registry", "TOOLS"), ("loglad_mcp.prompts.registry", "PROMPTS"),
                      ("loglad_mcp.resources.registry", "RESOURCES")):
        try:
            found.append(getattr(__import__(mod, fromlist=[name]), name))
        except ImportError as e:
            log.warning("%s not available yet (%s); registering none", mod, e)
            found.append([])
    try:
        from loglad_mcp.core.context import init_context
    except ImportError:
        init_context = None
    return *found, init_context


def _prompt(p) -> Prompt:
    def render(**args: str) -> str:
        return p.text + "".join(f"\n\n{k}: {v}" for k, v in args.items())

    return Prompt(name=p.name, description=p.description, fn=render,
                  arguments=[PromptArgument(name=a, required=True) for a in p.arguments])


def build_app() -> FastMCP:
    settings = load_settings()
    logging.basicConfig(stream=sys.stderr, level=settings.log_level,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    tools, prompts, resources, init_context = _registries()
    db = SereneDb(settings)
    if init_context:
        init_context(db, settings)  # no ping here: a down DB would stall Claude Code's MCP startup

    app = FastMCP("loglad")
    for t in tools:
        app.add_tool(t.fn, name=t.name, description=t.description)
    for p in prompts:
        app.add_prompt(_prompt(p))
    for r in resources:
        app.add_resource(FunctionResource.from_function(r.load, uri=r.uri, name=r.name, description=r.description,
                                                        mime_type="text/markdown"))
    log.info("loglad ready: %d tools, %d prompts, %d resources", len(tools), len(prompts), len(resources))
    return app


def main() -> None:
    build_app().run()  # stdio transport; never print to stdout


if __name__ == "__main__":
    main()

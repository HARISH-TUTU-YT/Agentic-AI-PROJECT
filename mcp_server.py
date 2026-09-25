import os
import sys

# Entrypoint forwarding to the Dine MCP Server
BACK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "back", "back")
if BACK_DIR not in sys.path:
    sys.path.insert(0, BACK_DIR)
os.chdir(BACK_DIR)

import mcp_server

if __name__ == "__main__":
    mcp_server.mcp.run(transport="stdio")

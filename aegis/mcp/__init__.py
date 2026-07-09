"""The MCP diagnostic gateway and server.

The agents call diagnostic tools only through the in-process gateway, which
stamps every call with the incident_id. Kindly note that the very same tools
are also served over the real MCP protocol by aegis.mcp.server.
"""

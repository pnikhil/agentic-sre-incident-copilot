"""The MCP diagnostic gateway and server.

The agents call diagnostic tools only through the in-process gateway, which
stamps every call with the incident_id. These tools are also served over MCP.
"""

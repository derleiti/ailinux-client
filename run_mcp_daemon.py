#!/usr/bin/env python3
"""
AILinux MCP Daemon - Hält Telemetrie-Verbindung zum Backend
"""
import asyncio
import sys
import os

# Environment setzen
os.environ['AILINUX_TOKEN'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjbGllbnRfaWQiOiJjbGllbnQtbXJrc2xlaXRlci0yYTljZDhlMTcyMWE3ZWFkIiwicm9sZSI6InBybyIsInN1YiI6Im1ya3NsZWl0ZXJtYW5uQGdtYWlsLmNvbSIsImV4cCI6MTc2ODUxODMzOCwiaWF0IjoxNzY1OTI2MzM4fQ.ALFbh9Z6buFidTkaGC343gw_u_A6ezndMLxXmT5Ab2w'
os.environ['AILINUX_TIER'] = 'pro'
os.environ['AILINUX_SERVER'] = 'https://api.ailinux.me'

sys.path.insert(0, '/home/zombie/projects/ailinux-client')
from ailinux_client.core.mcp_stdio_server import MCPStdioServer

async def main():
    server = MCPStdioServer()
    print(f'[DAEMON] Started with tier={server.tier}', file=sys.stderr)
    
    # Initialize
    request = {
        'jsonrpc': '2.0',
        'method': 'initialize',
        'params': {'clientInfo': {'name': 'ailinux-daemon', 'version': '2.2.0'}},
        'id': 1
    }
    await server.handle_request(request)
    print(f'[DAEMON] Initialized', file=sys.stderr)
    
    # Keep alive loop
    while True:
        try:
            await asyncio.sleep(30)
            if server._telemetry_ws:
                print(f'[DAEMON] Telemetrie aktiv', file=sys.stderr)
            else:
                print(f'[DAEMON] Telemetrie getrennt - warte auf Reconnect...', file=sys.stderr)
        except KeyboardInterrupt:
            print('[DAEMON] Stopping...', file=sys.stderr)
            break
        except Exception as e:
            print(f'[DAEMON] Error: {e}', file=sys.stderr)
    
    await server.close()

if __name__ == '__main__':
    asyncio.run(main())

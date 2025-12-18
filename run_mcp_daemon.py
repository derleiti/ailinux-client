#!/usr/bin/env python3
"""
AILinux MCP Daemon - Hält Telemetrie-Verbindung zum Backend
"""
import asyncio
import sys
import os

# Environment setzen
os.environ['AILINUX_TOKEN'] = ''
os.environ['AILINUX_TIER'] = 'pro'
os.environ['AILINUX_SERVER'] = 'https://api.ailinux.me'
os.environ['AILINUX_WSS_PORT'] = '44433'
os.environ['AILINUX_CLIENT_CERT'] = os.path.expanduser('~/.ailinux/certs/client.pem')
os.environ['AILINUX_CA_CERT'] = os.path.expanduser('~/.ailinux/certs/ca.crt')

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

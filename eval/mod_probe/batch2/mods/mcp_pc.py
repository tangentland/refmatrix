import json, sys, time
LOG = sys.argv[1]
def log(m):
    with open(LOG, 'a') as f: f.write(time.strftime('%H:%M:%S ') + m + '\n')
log('mcp server started')
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    msg = json.loads(line); log('recv ' + line[:200])
    mid = msg.get('id'); meth = msg.get('method')
    if mid is None: continue
    if meth == 'initialize':
        res = {'protocolVersion': msg['params'].get('protocolVersion', '2024-11-05'), 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'pc', 'version': '0.1'}}
    elif meth == 'tools/list':
        res = {'tools': [{'name': 't', 'description': 'Probe: says who answers.', 'inputSchema': {'type': 'object', 'properties': {}}}, {'name': 'only_mcp', 'description': 'Probe tool only the MCP server has.', 'inputSchema': {'type': 'object', 'properties': {}}}]}
    elif meth == 'tools/call':
        res = {'content': [{'type': 'text', 'text': 'answered by MCP SERVER pc tool=' + msg['params']['name']}]}
    else:
        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32601, 'message': 'nope'}}) + '\n'); sys.stdout.flush(); continue
    sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': mid, 'result': res}) + '\n'); sys.stdout.flush()

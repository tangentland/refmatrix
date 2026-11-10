import os, socket, sys, threading, time, http.server, socketserver
D = '/tmp/rp5'
LOG = sys.argv[1]
def log(m):
    with open(LOG, 'a') as f: f.write(time.strftime('%H:%M:%S') + ' ' + m + '\n')
for n in ('dead.sock', 'hang.sock', 'ok.sock', 'nonexist.sock'):
    try: os.unlink(os.path.join(D, n))
    except FileNotFoundError: pass
# b: socket file whose server is gone
s = socket.socket(socket.AF_UNIX); s.bind(D + '/dead.sock'); s.close()
# d: accept and never answer
hs = socket.socket(socket.AF_UNIX); hs.bind(D + '/hang.sock'); hs.listen(16)
held = []
def hang():
    while True:
        c, _ = hs.accept(); held.append(c); log('hang: accepted conn #%d' % len(held))
        def watch(c=c, i=len(held)):
            try:
                while True:
                    d = c.recv(4096)
                    if not d: log('hang: conn #%d closed by client' % i); return
                    log('hang: conn #%d got %d bytes' % (i, len(d)))
            except Exception as e: log('hang: conn #%d err %r' % (i, e))
        threading.Thread(target=watch, daemon=True).start()
threading.Thread(target=hang, daemon=True).start()
# e: working http server
class H(http.server.BaseHTTPRequestHandler):
    def address_string(self): return 'unix'
    def do_GET(self):
        b = ('hello from unix http path=%s' % self.path).encode()
        self.send_response(200); self.send_header('Content-Type', 'text/plain'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
        log('ok: served %s host=%s' % (self.path, self.headers.get('Host')))
class U(socketserver.ThreadingMixIn, socketserver.UnixStreamServer): daemon_threads = True
srv = U(D + '/ok.sock', H)
log('servers up pid=%d' % os.getpid())
srv.serve_forever()

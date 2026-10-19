"""Windows-only loopback bridge from VS Code to authenticated Colab Qwen endpoint.
Run: python windows_bridge.py
Python standard library only. Does NOT forward requests to arbitrary websites.
"""
import getpass, json, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

url=input('Paste Kaggle TUNNEL URL: ').strip().rstrip('/')
if not re.fullmatch(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com',url):
    raise SystemExit('Expected a https://...trycloudflare.com tunnel URL')
token=getpass.getpass('Paste ACCESS TOKEN (input hidden): ').strip()
if len(token)<30: raise SystemExit('Token looks incomplete')
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path!='/explain': self.send_error(404);return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>20000: self.send_error(413);return
            raw=self.rfile.read(size)
            payload=json.loads(raw)
            if payload.get('task')!='explain_maintainability_evidence':
                self.send_error(422);return
            req=Request(url+'/explain',data=json.dumps(payload).encode(),method='POST',headers={
                'Content-Type':'application/json','Authorization':'Bearer '+token})
            with urlopen(req,timeout=85) as response:
                output=response.read(50000)
            result=json.loads(output)
            if not isinstance(result.get('explanation'),str): raise ValueError('No explanation returned')
            response_bytes=json.dumps({'explanation':result['explanation']}).encode()
            self.send_response(200)
        except HTTPError as ex:
            response_bytes=json.dumps({'error':'Remote Qwen service HTTP '+str(ex.code)}).encode()
            self.send_response(502)
        except (URLError,TimeoutError,ValueError,KeyError) as ex:
            response_bytes=json.dumps({'error':str(ex)}).encode()
            self.send_response(502)
        except Exception as ex:
            response_bytes=json.dumps({'error':type(ex).__name__}).encode()
            self.send_response(502)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(response_bytes)))
        self.end_headers();self.wfile.write(response_bytes)
    def do_GET(self):self.send_error(404)
    def log_message(self,fmt,*args): print('Request:',fmt%args)
print('Bridge active: http://127.0.0.1:8765/explain')
print('Keep this PowerShell window open. Press Ctrl+C to stop.')
ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()

"""Web dashboard for the rover (standard library only). Run: python3 server.py [--sim] [--port 8000]"""
import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from rover import Rover

TOKEN = os.environ.get("ROVER_TOKEN", "")     # optional: set it, then open http://rover:8000/#token=YOURTOKEN


def _num(v, lo, hi, default):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


class Handler(BaseHTTPRequestHandler):
    rover = None

    def log_message(self, *a):
        pass

    def _authed(self):
        if not TOKEN:
            return True
        q = parse_qs(urlparse(self.path).query)
        return self.headers.get("X-Token") == TOKEN or q.get("token", [""])[0] == TOKEN

    def _send(self, code, body, ctype="application/json"):
        if not isinstance(body, (bytes, str)):
            body = json.dumps(body, default=lambda o: o.item() if hasattr(o, "item") else str(o))
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if not self._authed():
            return self._send(401, {"error": "bad token"})
        r = self.rover
        if path == "/api/state":
            return self._send(200, r.state())
        if path == "/api/samples":
            return self._send(200, r.samples)
        if path == "/api/export.csv":
            return self._send(200, r.to_csv(), "text/csv")
        if path == "/stream.mjpg":
            return self._stream()
        self._send(404, {"error": "not found"})

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        seq = -1
        try:
            while True:
                seq, jpg = self.rover.camera.wait_new(seq)
                if jpg:
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg))
                    self.wfile.write(jpg + b"\r\n")
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def do_POST(self):
        if not self._authed():
            return self._send(401, {"error": "bad token"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            b = json.loads(self.rfile.read(n)) if n else {}
        except ValueError:
            return self._send(400, {"error": "bad json"})
        r, path = self.rover, urlparse(self.path).path
        if path == "/api/drive":
            ok = r.drive(_num(b.get("l"), -1, 1, 0), _num(b.get("r"), -1, 1, 0))
        elif path == "/api/stop":
            r.stop()
            ok = True
        elif path == "/api/probe":
            ok = r.move_probe(bool(b.get("down")))
        elif path == "/api/laser":
            r.set_laser(bool(b.get("on")))
            ok = True
        elif path == "/api/sample":
            ok = r.start_sample()
        elif path == "/api/survey":
            ok = r.start_survey(int(_num(b.get("n"), 1, 50, 3)), _num(b.get("step_mm"), 50, 5000, 500),
                                _num(b.get("speed"), 0.2, 1, 0.6))
        else:
            return self._send(404, {"error": "not found"})
        self._send(200, {"ok": bool(ok)})


PAGE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Soil Rover</title>
<style>
:root{--bg:#f6f4f1;--fg:#1c1b19;--card:#fff;--line:#d9d4cc;--mut:#6b655c;--acc:#e8650a}
@media(prefers-color-scheme:dark){:root{--bg:#141311;--fg:#f1eee9;--card:#201e1b;--line:#3a3631;--mut:#a39c92}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif;padding:10px;max-width:760px;margin:auto}
h1{font-size:18px;margin:4px 0 8px}h2{font-size:14px;margin:0 0 6px;color:var(--mut);font-weight:600}
.c{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px;margin-bottom:10px}
img{width:100%;border-radius:8px;background:#000;display:block}
button{font:inherit;padding:10px 14px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--fg);touch-action:manipulation}
button.p{background:var(--acc);border-color:var(--acc);color:#fff}button.s{background:#c62828;border-color:#c62828;color:#fff;font-weight:700}
.pad{display:grid;grid-template-columns:repeat(3,64px);gap:6px;justify-content:center;margin:6px 0}.pad button{height:64px;font-size:22px;user-select:none}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:6px 0}input[type=number]{width:80px;padding:8px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--fg)}
.k{color:var(--mut)}table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:4px 6px;border-bottom:1px solid var(--line);text-align:left}
canvas{width:100%;height:220px;border-radius:8px;background:var(--bg);border:1px solid var(--line)}
</style></head><body>
<h1>Soil Rover</h1>
<div class="c"><img id="cam" alt="camera"><div class="row"><span id="st" class="k">connecting...</span></div></div>
<div class="c"><h2>Drive</h2>
<div class="pad"><span></span><button data-d="f">&#9650;</button><span></span><button data-d="l">&#9664;</button><button data-d="b">&#9660;</button><button data-d="r">&#9654;</button></div>
<div class="row"><span class="k">Speed</span><input id="sp" type="range" min="0.2" max="1" step="0.05" value="0.6" style="flex:1"><button class="s" id="stop">STOP</button></div></div>
<div class="c"><h2>Soil tools</h2>
<div class="row"><button id="pd">Probe down</button><button id="pu">Probe up</button><button id="lz">Laser</button></div>
<div class="row"><button class="p" id="smp">Sample here</button><span class="k">Survey</span><input id="sn" type="number" value="4" min="1" max="50"> stops every <input id="ss" type="number" value="500" min="50" max="5000"> mm<button class="p" id="sv">Go</button></div></div>
<div class="c"><h2>Latest result</h2><div id="last" class="k">No samples yet.</div></div>
<div class="c"><h2>Water spots (wettest first)</h2><div id="wat" class="k">-</div><canvas id="map" width="700" height="440"></canvas></div>
<div class="c"><h2>All samples</h2><div style="overflow:auto"><table id="tb"></table></div><div class="row"><a href="#" id="csv">Download CSV</a></div></div>
<script>
const T=new URLSearchParams(location.hash.slice(1)).get('token')||'';const Q=T?'?token='+encodeURIComponent(T):'';
const HD={'Content-Type':'application/json'};if(T)HD['X-Token']=T;
const post=(p,b)=>fetch(p,{method:'POST',headers:HD,body:JSON.stringify(b||{})}).then(r=>r.json()).catch(()=>({}));
const get=p=>fetch(p+Q,{headers:T?{'X-Token':T}:{}}).then(r=>r.json());
document.getElementById('cam').src='/stream.mjpg'+Q;
document.getElementById('csv').href='/api/export.csv'+Q;
const sp=()=>+document.getElementById('sp').value;let tm=null,cur=null;
const MAP={f:s=>[s,s],b:s=>[-s,-s],l:s=>[-s*.8,s*.8],r:s=>[s*.8,-s*.8]};
function go(d){cur=d;clearInterval(tm);const send=()=>{const[l,r]=MAP[cur](sp());post('/api/drive',{l,r})};send();tm=setInterval(send,150)}
function halt(){cur=null;clearInterval(tm);post('/api/drive',{l:0,r:0})}
document.querySelectorAll('.pad button').forEach(b=>{b.onpointerdown=e=>{e.preventDefault();go(b.dataset.d)};b.onpointerup=b.onpointerleave=b.onpointercancel=halt});
const KEY={ArrowUp:'f',w:'f',ArrowDown:'b',s:'b',ArrowLeft:'l',a:'l',ArrowRight:'r',d:'r'};
addEventListener('keydown',e=>{const d=KEY[e.key];if(d&&cur!==d&&!e.repeat)go(d)});addEventListener('keyup',e=>{if(KEY[e.key])halt()});
document.getElementById('stop').onclick=()=>post('/api/stop');
document.getElementById('pd').onclick=()=>post('/api/probe',{down:true});document.getElementById('pu').onclick=()=>post('/api/probe',{down:false});
let lz=false;document.getElementById('lz').onclick=()=>{lz=!lz;post('/api/laser',{on:lz})};
document.getElementById('smp').onclick=()=>post('/api/sample');
document.getElementById('sv').onclick=()=>post('/api/survey',{n:+sn.value,step_mm:+ss.value,speed:sp()});
const f1=(v,d=1)=>v==null?'-':(+v).toFixed(d);
function last(s){if(!s){return'No samples yet.'}const o=s.soil||{};let h=`<b>#${s.id} ${s.soil_label||'(no camera data)'}</b><br>texture ${s.texture||'-'}, roughness ${f1(s.laser&&s.laser.roughness_mm,2)} mm`;
 if(s.soil)h+=`<br>moisture ${o.moisture}% (${s.moisture_class}), pH ${o.ph}, temp ${o.temp_c}&deg;C<br>N ${o.n} (${s.levels.n}), P ${o.p} (${s.levels.p}), K ${o.k} (${s.levels.k}) mg/kg`;
 if(s.crops)h+='<br><b>Suggested crops</b><ol style="margin:4px 0 0;padding-left:20px">'+s.crops.map(c=>`<li>${c.name} (${c.score})${c.notes.length?' <span class="k">- '+c.notes.join('; ')+'</span>':''}</li>`).join('')+'</ol>';
 if(s.errors&&s.errors.length)h+='<br><span style="color:#c62828">'+s.errors.join('<br>')+'</span>';return h}
async function poll(){try{const s=await get('/api/state');const g=s.gps;
 st.textContent=`${s.busy?s.busy+': ':''}${s.msg} | probe ${s.probe} | GPS ${g?f1(g.lat,5)+', '+f1(g.lon,5):'no fix'} | ${s.distance_mm} mm`;
 document.getElementById('last').innerHTML=last(s.last);
 wat.innerHTML=s.water.length?s.water.map(w=>`#${w.id}: ${w.moisture}% (score ${w.score})`).join(' &middot; '):'-';
 if(s.n_samples!==N){N=s.n_samples;table()}}catch(e){st.textContent='no connection'}}
let N=-1;const st=document.getElementById('st'),wat=document.getElementById('wat'),sn=document.getElementById('sn'),ss=document.getElementById('ss');
async function table(){const a=await get('/api/samples');const tb=document.getElementById('tb');
 tb.innerHTML='<tr><th>#</th><th>Soil</th><th>Moist %</th><th>pH</th><th>N-P-K</th><th>Top crop</th></tr>'+a.slice().reverse().map(s=>{const o=s.soil||{};return`<tr><td>${s.id}</td><td>${s.soil_class||'-'}</td><td>${f1(o.moisture)}</td><td>${f1(o.ph)}</td><td>${o.n??'-'}-${o.p??'-'}-${o.k??'-'}</td><td>${s.crops?s.crops[0].name:'-'}</td></tr>`}).join('');draw(a)}
function draw(a){const c=document.getElementById('map'),x=c.getContext('2d');x.clearRect(0,0,c.width,c.height);const P=a.filter(s=>s.gps&&s.gps.lat!=null&&s.soil);if(!P.length)return;
 const la=P[0].gps.lat,lo=P[0].gps.lon,k=111320,pt=P.map(s=>({x:(s.gps.lon-lo)*k*Math.cos(la*Math.PI/180),y:(s.gps.lat-la)*k,m:s.soil.moisture,id:s.id}));
 const xs=pt.map(p=>p.x),ys=pt.map(p=>p.y),x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys),sc=Math.min(600/Math.max(x1-x0,1),340/Math.max(y1-y0,1),60);
 const mx=Math.max(...pt.map(p=>p.m),1),best=pt.reduce((b,p)=>p.m>b.m?p:b);
 pt.forEach(p=>{const px=350+(p.x-(x0+x1)/2)*sc,py=220-(p.y-(y0+y1)/2)*sc;x.beginPath();x.arc(px,py,14,0,7);x.fillStyle=`rgba(30,110,220,${.2+.8*p.m/mx})`;x.fill();
  if(p===best){x.lineWidth=3;x.strokeStyle='#e8650a';x.stroke()}x.fillStyle='#fff';x.font='bold 13px sans-serif';x.textAlign='center';x.fillText(p.id,px,py+5)})}
poll();setInterval(poll,1000);
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true", help="simulate all hardware (for testing on a laptop)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--data", default=None, help="folder for samples.jsonl and photos")
    a = ap.parse_args()
    Handler.rover = Rover(sim=a.sim, data_dir=a.data)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    srv.daemon_threads = True
    print(f"Rover dashboard on http://{a.host}:{a.port}/  (sim={a.sim}, token {'set' if TOKEN else 'not set'})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        Handler.rover.motors.stop()
        Handler.rover.laser.set(False)


if __name__ == "__main__":
    main()

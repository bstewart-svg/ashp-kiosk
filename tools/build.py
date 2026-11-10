#!/usr/bin/env python3
"""Assemble the kiosk site from the converter output.

build.py <repo-dir> <fonts-dir> deck:title:srcdir ...
"""
import sys, os, json, shutil, subprocess, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
repo, fonts = sys.argv[1], sys.argv[2]
decks = [a.split(':', 2) for a in sys.argv[3:]]

os.makedirs(os.path.join(repo, 'fonts'), exist_ok=True)
for f in os.listdir(fonts):
    if f.endswith('.woff2'):
        shutil.copy(os.path.join(fonts, f), os.path.join(repo, 'fonts', f))
FONT_FILES = sorted(f for f in os.listdir(os.path.join(repo, 'fonts')) if f.endswith('.woff2'))

FONT_CSS = """
@font-face{font-family:'Archivo';src:url(../fonts/Archivo-100_900.woff2) format('woff2');font-weight:100 900;font-stretch:62% 125%;font-display:block}
@font-face{font-family:'Funnel Sans';src:url(../fonts/FunnelSans-300_800.woff2) format('woff2');font-weight:300 800;font-display:block}
@font-face{font-family:'IBM Plex Mono';src:url(../fonts/IBMPlexMono-400.woff2) format('woff2');font-weight:400;font-display:block}
@font-face{font-family:'IBM Plex Mono';src:url(../fonts/IBMPlexMono-500.woff2) format('woff2');font-weight:500;font-display:block}
@font-face{font-family:'IBM Plex Mono';src:url(../fonts/IBMPlexMono-600.woff2) format('woff2');font-weight:600 700;font-display:block}
@font-face{font-family:'Barlow';src:url(../fonts/Barlow-400.woff2) format('woff2');font-weight:400;font-display:block}
@font-face{font-family:'Barlow';src:url(../fonts/Barlow-500.woff2) format('woff2');font-weight:500;font-display:block}
@font-face{font-family:'Barlow';src:url(../fonts/Barlow-600.woff2) format('woff2');font-weight:600 700;font-display:block}
"""

CSS = r"""
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:#05080d;overflow:hidden;-webkit-tap-highlight-color:transparent;
  user-select:none;-webkit-user-select:none;touch-action:none;overscroll-behavior:none;cursor:default}
#vp{position:fixed;inset:0;display:flex;align-items:center;justify-content:center}
#stage{position:relative;width:1920px;height:1080px;flex:none;transform-origin:center center;overflow:hidden;background:#05080d}
.slide{position:absolute;inset:0;opacity:0;visibility:hidden;transition:opacity .9s ease,visibility 0s linear .9s;contain:strict}
.slide.on{opacity:1;visibility:visible;transition:opacity .9s ease,visibility 0s}
.L{position:absolute;inset:0;pointer-events:none}
.s,.pic{position:absolute}
.grp{position:absolute;inset:0}
svg.g{position:absolute;overflow:visible}
.pic{overflow:hidden}
.pic img{position:absolute;display:block;max-width:none}
.pic .bd{position:absolute;inset:0}
.tx{position:absolute;inset:0;display:flex;flex-direction:column;overflow:visible;
  text-rendering:geometricPrecision;-webkit-font-smoothing:antialiased;font-kerning:normal}
.tx p{white-space:pre-wrap;overflow-wrap:break-word}
.tx[style*=nowrap] p{white-space:pre}
.bu{display:inline-block;width:1em}

/* Entrance: soft fade with a short upward drift, staggered by reading order */
.L.fg{opacity:0;transform:translate3d(0,14px,0);will-change:opacity,transform}
.slide.in .L.fg{opacity:1;transform:none;
  transition:opacity 1.1s cubic-bezier(.22,.61,.36,1) calc(.25s + var(--i)*.07s),
             transform 1.4s cubic-bezier(.22,.61,.36,1) calc(.25s + var(--i)*.07s)}
/* Full-bleed photos drift very slowly while the slide is up */
.pic.kb img{transform:scale(1.0);transition:transform 0s}
.slide.in .pic.kb img{transform:scale(1.035);transition:transform 16s linear}
@media (prefers-reduced-motion:reduce){
  .L.fg,.slide.in .L.fg{transform:none;transition:opacity .6s ease}
  .slide.in .pic.kb img{transform:none}
}

/* Controls: discreet, bottom centre */
#ctl{position:fixed;left:50%;bottom:max(14px,env(safe-area-inset-bottom));transform:translateX(-50%);
  display:flex;align-items:center;gap:6px;padding:6px;border-radius:999px;
  background:rgba(8,14,24,.42);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
  border:1px solid rgba(255,255,255,.12);z-index:10;opacity:.55;transition:opacity .5s ease}
#ctl.awake{opacity:1}
#ctl button{appearance:none;border:0;background:none;color:#fff;width:52px;height:52px;border-radius:999px;
  display:flex;align-items:center;justify-content:center;cursor:pointer;opacity:.9}
#ctl button:active{background:rgba(255,255,255,.14)}
#ctl svg{width:22px;height:22px;fill:currentColor}
#dots{display:flex;gap:7px;padding:0 10px}
#dots i{display:block;width:6px;height:6px;border-radius:50%;background:rgba(255,255,255,.32);transition:background .4s,transform .4s}
#dots i.on{background:#fff;transform:scale(1.25)}
#bar{position:absolute;left:0;right:0;bottom:0;height:2px;background:rgba(255,255,255,.08);border-radius:2px;overflow:hidden;margin:0 22px}
#bar b{display:block;height:100%;width:0;background:rgba(255,255,255,.55)}
#cache{position:fixed;left:50%;top:14px;transform:translateX(-50%);font:600 13px/1 'IBM Plex Mono',monospace;
  letter-spacing:.08em;color:#fff;background:rgba(0,0,0,.6);padding:8px 14px;border-radius:6px;z-index:11;display:none}
#cache.ok{background:#1b6b3a}
"""

JS = r"""
(function(){
  var stage=document.getElementById('stage'), slides=[].slice.call(stage.querySelectorAll('.slide'));
  var dots=document.getElementById('dots'), bar=document.querySelector('#bar b'), ctl=document.getElementById('ctl');
  var playBtn=document.getElementById('play'), N=slides.length, cur=-1, playing=true, timer=null, t0=0, dwell=0;
  var RESUME=45000, resumeT=null, wakeT=null;
  slides.forEach(function(){ dots.appendChild(document.createElement('i')); });

  function fit(){ var s=Math.min(innerWidth/1920, innerHeight/1080); stage.style.transform='scale('+s+')'; }
  addEventListener('resize',fit); fit();

  function show(n){
    n=(n+N)%N; if(n===cur) return;
    var prev=slides[cur]; cur=n; var el=slides[n];
    if(prev){ prev.classList.remove('on'); setTimeout(function(p){ return function(){ if(p!==slides[cur]) p.classList.remove('in'); }; }(prev), 950); }
    el.classList.remove('in'); void el.offsetWidth; el.classList.add('on');
    requestAnimationFrame(function(){ requestAnimationFrame(function(){ el.classList.add('in'); }); });
    [].forEach.call(dots.children,function(d,i){ d.classList.toggle('on',i===n); });
    schedule();
  }
  function schedule(){
    clearTimeout(timer); bar.style.transition='none'; bar.style.width='0';
    if(!playing||cur<0) return;
    dwell=+slides[cur].dataset.adv||7000; t0=Date.now();
    void bar.offsetWidth; bar.style.transition='width '+dwell+'ms linear'; bar.style.width='100%';
    timer=setTimeout(function(){ show(cur+1); }, dwell);
  }
  var PLAY='<svg viewBox="0 0 24 24"><path d="M7 4.5v15l13-7.5z"/></svg>', PAUSE='<svg viewBox="0 0 24 24"><path d="M6 4h4v16H6zM14 4h4v16h-4z"/></svg>';
  function setPlaying(p){
    playing=p; playBtn.innerHTML=p?PAUSE:PLAY; playBtn.setAttribute('aria-label',p?'Pause':'Play');
    clearTimeout(resumeT); if(!p) resumeT=setTimeout(function(){ setPlaying(true); }, RESUME);
    schedule();
  }
  function wake(){ ctl.classList.add('awake'); clearTimeout(wakeT); wakeT=setTimeout(function(){ ctl.classList.remove('awake'); }, 4000); }

  // Manual navigation pauses autoplay; it resumes on its own after 45 s untouched.
  function manual(d){ show(cur+d); setPlaying(false); }
  document.getElementById('prev').addEventListener('click',function(e){ e.stopPropagation(); wake(); manual(-1); });
  document.getElementById('next').addEventListener('click',function(e){ e.stopPropagation(); wake(); manual(1); });
  playBtn.addEventListener('click',function(e){ e.stopPropagation(); wake(); if(!playing) show(cur+1); setPlaying(!playing); });
  ctl.addEventListener('pointerdown',function(e){ e.stopPropagation(); });

  // Touch: tap right side = next, left side = back, swipe either way.
  var sx=0, sy=0, st=0, down=false;
  addEventListener('pointerdown',function(e){ down=true; sx=e.clientX; sy=e.clientY; st=Date.now(); wake(); },{passive:true});
  addEventListener('pointerup',function(e){
    if(!down) return; down=false;
    if(e.target.closest && e.target.closest('#ctl')) return;
    var dx=e.clientX-sx, dy=e.clientY-sy;
    if(Math.abs(dx)>60 && Math.abs(dx)>Math.abs(dy)*1.2){ manual(dx<0?1:-1); return; }
    if(Math.abs(dx)<20 && Math.abs(dy)<20 && Date.now()-st<600){ manual(e.clientX>innerWidth/2?1:-1); }
  },{passive:true});
  addEventListener('keydown',function(e){
    if(e.key==='ArrowRight'||e.key==='PageDown') manual(1);
    else if(e.key==='ArrowLeft'||e.key==='PageUp') manual(-1);
    else if(e.key===' '){ e.preventDefault(); setPlaying(!playing); }
  });
  addEventListener('contextmenu',function(e){ e.preventDefault(); });
  document.addEventListener('visibilitychange',function(){ if(!document.hidden) schedule(); });

  // Start once fonts and the first slide's images are ready, so nothing pops in.
  function start(){ setPlaying(true); show(0); }
  var ready=document.fonts&&document.fonts.ready?document.fonts.ready:Promise.resolve();
  var imgs=[].slice.call(slides[0].querySelectorAll('img')).map(function(i){ return i.decode?i.decode().catch(function(){}):0; });
  Promise.race([Promise.all([ready].concat(imgs)), new Promise(function(r){ setTimeout(r,2500); })]).then(start);

  // Offline cache
  var badge=document.getElementById('cache'), showBadge=/[?&]cache/.test(location.search);
  if('serviceWorker' in navigator && location.protocol!=='file:'){
    navigator.serviceWorker.register('sw.js').then(function(){ return navigator.serviceWorker.ready; }).then(function(reg){
      var urls=ASSETS.map(function(u){ return new URL(u,location.href).href; });
      (reg.active||navigator.serviceWorker.controller).postMessage({type:'PRECACHE',urls:urls});
    }).catch(function(){});
    navigator.serviceWorker.addEventListener('message',function(e){
      var m=e.data||{}; if(m.type!=='PRECACHE_PROGRESS'||!showBadge) return;
      badge.style.display='block';
      if(m.finished && m.done===m.total){ badge.textContent='CACHED — RUNS OFFLINE ('+m.total+' FILES)'; badge.className='ok'; }
      else badge.textContent='CACHING '+m.done+' / '+m.total;
    });
  }
})();
"""

SW = r"""/* ASHP Midyear kiosk (__DECK__) - offline cache.
 * index.html / sw.js: network first, falling back to cache.
 * media / fonts: cache first. Replacing a file under the same name? Bump CACHE.
 */
var CACHE = 'ashp-__DECK__-__VER__';
self.addEventListener('install', function(e){
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(function(c){ return c.addAll(['./','./index.html']); }).catch(function(){}));
});
self.addEventListener('activate', function(e){
  e.waitUntil(caches.keys().then(function(keys){
    return Promise.all(keys.map(function(k){ return (k.indexOf('ashp-__DECK__-')===0 && k!==CACHE) ? caches.delete(k) : null; }));
  }).then(function(){ return self.clients.claim(); }));
});
function isDoc(req){ if(req.mode==='navigate') return true; return /\/$|index\.html$|sw\.js$/.test(new URL(req.url).pathname); }
function put(req,res){ if(res && res.status===200 && res.type==='basic'){ var c=res.clone(); caches.open(CACHE).then(function(x){ x.put(req,c); }); } return res; }
self.addEventListener('fetch', function(e){
  if(e.request.method!=='GET' || new URL(e.request.url).origin!==self.location.origin) return;
  if(isDoc(e.request)){
    e.respondWith(fetch(e.request).then(function(r){ return put(e.request,r); }).catch(function(){
      return caches.match(e.request,{ignoreSearch:true}).then(function(h){ return h || caches.match('./index.html'); });
    }));
    return;
  }
  e.respondWith(caches.match(e.request,{ignoreSearch:true}).then(function(h){
    return h || fetch(e.request).then(function(r){ return put(e.request,r); });
  }));
});
self.addEventListener('message', function(e){
  var m=e.data||{}; if(m.type!=='PRECACHE'||!m.urls) return;
  e.waitUntil(caches.open(CACHE).then(function(c){
    var urls=m.urls, i=0, stored=0;
    function report(done){ self.clients.matchAll().then(function(cs){ cs.forEach(function(cl){ cl.postMessage({type:'PRECACHE_PROGRESS',done:stored,total:urls.length,finished:!!done}); }); }); }
    function step(){
      if(i>=urls.length){ report(true); return Promise.resolve(); }
      var u=urls[i++];
      return c.match(u).then(function(h){
        if(h){ stored++; report(); return step(); }
        return fetch(u,{cache:'no-cache'}).then(function(r){ if(r && r.status===200) return c.put(u,r.clone()); })
          .then(function(){ stored++; report(); return step(); }).catch(function(){ return step(); });
      });
    }
    return step();
  }));
});
"""

PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-capable" content="yes">
<title>__TITLE__</title>
<style>__FONTCSS____CSS__</style>
</head><body>
<div id="vp"><div id="stage">
__SLIDES__
</div></div>
<div id="ctl" role="toolbar" aria-label="Slideshow controls">
  <button id="prev" aria-label="Previous"><svg viewBox="0 0 24 24"><path d="M15.5 4.5 8 12l7.5 7.5-1.6 1.6L4.8 12l9.1-9.1z"/></svg></button>
  <button id="play" aria-label="Pause"></button>
  <span id="dots"></span>
  <button id="next" aria-label="Next"><svg viewBox="0 0 24 24"><path d="M8.5 4.5 16 12l-7.5 7.5 1.6 1.6 9.1-9.1-9.1-9.1z"/></svg></button>
  <div id="bar"><b></b></div>
</div>
<div id="cache"></div>
<script>var ASSETS=__ASSETS__;</script>
<script>__JS__</script>
</body></html>
"""

index_links = []
for deck, title, src in decks:
    out = os.path.join(repo, deck)
    if os.path.exists(os.path.join(out, 'media')):
        shutil.rmtree(os.path.join(out, 'media'))
    subprocess.run([sys.executable, os.path.join(HERE, 'convert.py'), src, out, deck, title], check=True)
    data = json.load(open(os.path.join(out, 'slides.build.json')))
    os.remove(os.path.join(out, 'slides.build.json'))
    secs = []
    for i, s in enumerate(data['slides']):
        secs.append('<section class="slide" data-adv="%d" style="%s" aria-label="Slide %d">%s</section>' % (
            s['adv'], s['bg'], i + 1, s['html']))
    assets = ['./', './index.html'] + ['./' + m for m in data['media']] + ['../fonts/' + f for f in FONT_FILES]
    page = (PAGE.replace('__TITLE__', title).replace('__FONTCSS__', FONT_CSS).replace('__CSS__', CSS)
            .replace('__SLIDES__', '\n'.join(secs)).replace('__ASSETS__', json.dumps(assets)).replace('__JS__', JS))
    open(os.path.join(out, 'index.html'), 'w').write(page)
    h = hashlib.sha1()
    for m in data['media']:
        h.update(open(os.path.join(out, m), 'rb').read())
    for f in FONT_FILES:
        h.update(f.encode())
    open(os.path.join(out, 'sw.js'), 'w').write(SW.replace('__DECK__', deck).replace('__VER__', h.hexdigest()[:10]))
    size = sum(os.path.getsize(os.path.join(out, m)) for m in data['media'])
    index_links.append((deck, title, len(data['slides']), size))
    print('  built', deck, len(data['slides']), 'slides', '%.1f MB' % (size / 1e6))

rows = '\n'.join('<a href="%s/"><b>%s</b><span>%d slides</span></a>' % (d, t, n) for d, t, n, s in index_links)
open(os.path.join(repo, 'index.html'), 'w').write("""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>ASHP Midyear 2026 Kiosks</title>
<style>%s
body{margin:0;min-height:100vh;background:#0c1729;color:#fff;font-family:'Funnel Sans',sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:28px;padding:24px}
h1{font:400 28px/1.2 'Archivo';font-stretch:125%%;margin:0}
nav{display:grid;gap:12px;width:min(520px,100%%)}
a{display:flex;justify-content:space-between;align-items:center;padding:20px 24px;border-radius:12px;border:1px solid rgba(255,255,255,.16);background:rgba(255,255,255,.05);color:#fff;text-decoration:none;font-size:20px}
a span{font:13px 'IBM Plex Mono';letter-spacing:.1em;text-transform:uppercase;opacity:.6}
</style></head><body><h1>ASHP Midyear 2026</h1><nav>%s</nav></body></html>""" % (FONT_CSS.replace('../fonts/', 'fonts/'), rows))
open(os.path.join(repo, 'robots.txt'), 'w').write('User-agent: *\nDisallow: /\n')
open(os.path.join(repo, '.nojekyll'), 'w').write('')

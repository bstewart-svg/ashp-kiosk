/* ASHP Midyear kiosk (home) - offline cache.
 * index.html / sw.js: network first, falling back to cache.
 * media / fonts: cache first. Replacing a file under the same name? Bump CACHE.
 */
var CACHE = 'ashp-home-3a363bffce';
self.addEventListener('install', function(e){
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(function(c){ return c.addAll(['./','./index.html']); }).catch(function(){}));
});
self.addEventListener('activate', function(e){
  e.waitUntil(caches.keys().then(function(keys){
    return Promise.all(keys.map(function(k){ return (k.indexOf('ashp-home-')===0 && k!==CACHE) ? caches.delete(k) : null; }));
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

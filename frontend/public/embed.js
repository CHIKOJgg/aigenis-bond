/* Bonds Engine · Aigenis Embed v2.0 — BCSE + MOEX support
   Usage: <script src="embed.js" data-api="/api/v1" data-market="bcse"></script>
   Or:    <bonds-engine market="moex"></bonds-engine>
*/
(function(){
  var s = document.currentScript;
  var api = s.getAttribute('data-api')||'/api/v1';
  var market = s.getAttribute('data-market')||'';
  var target = document.getElementById('bonds-engine-container')||document.querySelector('bonds-engine');
  if(!target){target=document.createElement('div');target.id='bonds-engine-container';document.body.appendChild(target);}
  if(!market&&target){market=target.getAttribute('market')||target.getAttribute('data-market')||'';}
  if(!market){
    var host=window.location.hostname||'';
    market=host.indexOf('moex')>=0?'moex':host.indexOf('bcse')>=0?'bcse':'';
  }
  if(!market)market='bcse';

  var base=s.src?s.src.replace(/\/[^\/]+$/,''):'.';
  var widgetFile=market==='moex'?'moex-bond-analyzer.html':'bcse-bond-analyzer.html';

  var link=document.createElement('link');
  link.rel='stylesheet';link.href=base+'/aigenis-widget.css';
  document.head.appendChild(link);

  var iframe=document.createElement('iframe');
  iframe.src=base+'/'+widgetFile;
  iframe.style.cssText='width:100%;height:100vh;border:none;display:block;';
  iframe.setAttribute('sandbox','allow-scripts allow-same-origin allow-forms allow-popups');
  target.appendChild(iframe);
})();

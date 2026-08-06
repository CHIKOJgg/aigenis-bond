/* be-widget-core.js v2.0 — shared core for BCSE and MOEX bond analyzer widgets */
(function(){
'use strict';
window.BE = BE;
var API='', MARKET='bcse';

function BE(){}

var bonds=[], scores={}, loading=!0, error=null, currency='', search='', sortKey='score', sortDir='desc', page=0;
var PS=25;
var T=function(s,d){return s!=null&&s!==''?s:(d||'--');};
var FP=function(v,d){return v!=null?Number(v).toFixed(2)+'%':(d||'--');};
var FD=function(d){if(!d)return'--';try{return new Date(d).toLocaleDateString('ru-RU',{day:'2-digit',month:'short',year:'numeric'});}catch{return d;}};
var DAYS=function(d){if(!d)return null;try{return Math.ceil((new Date(d)-Date.now())/864e5);}catch{return null;}};
var TIER_MAP={'S':'t-S','A':'t-A','B':'t-B','C':'t-C','D':'t-D'};
var VERDICT={'S':'Исключительная возможность','A':'Хорошая возможность','B':'Умеренно интересна','C':'Средняя','D':'Слабая / избегать'};
var VCLS={'S':'v-S','A':'v-A','B':'v-B','C':'v-C','D':'v-D'};
var FL={'yield_component':'Доходность','currency_component':'Валюта','duration_component':'Дюрация','liquidity_component':'Ликвидность','metal_component':'Драгметалл','credit_risk_component':'Кредитный риск','inflation_component':'Инфляция','coupon_component':'Купон','volatility_component':'Волатильность'};

var BCSE_CURS=[{k:'',l:'Все'},{k:'USD',l:'USD'},{k:'BYN',l:'BYN'},{k:'EUR',l:'EUR'},{k:'XAU',l:'Золото'},{k:'XAG',l:'Серебро'},{k:'XPT',l:'Платина'}];
var MOEX_CURS=[{k:'',l:'Все'},{k:'RUB',l:'RUB'},{k:'USD',l:'USD'},{k:'EUR',l:'EUR'},{k:'CNY',l:'CNY'},{k:'XAU',l:'Золото'}];
var CURS = BCSE_CURS;

var marketLabel = 'BCSE';
var marketColor = '#004b65';

BE.init = function(apiUrl, market) {
  API = (apiUrl||'/api/v1').replace(/\/$/,'');
  MARKET = market||'bcse';
  CURS = MARKET==='moex'?MOEX_CURS:BCSE_CURS;
  marketLabel = MARKET==='moex'?'MOEX':'BCSE';
  marketColor = MARKET==='moex'?'#e03400':'#004b65';
  fetchData();
};

function fetchData(){
  loading=!0;error=null;render();
  var url = API+'/bonds?limit=2000&market='+MARKET;
  if(currency) url += '&currency='+currency;
  fetch(url).then(function(r){if(!r.ok)throw Error('API: '+r.status);return r.json();})
  .then(function(b){bonds=b;return fetch(API+'/scores?market='+MARKET).then(function(r){return r.ok?r.json():[];}).catch(function(){return[];});})
  .then(function(s){s.forEach(function(x){scores[x.internal_id]=x;});loading=!1;render();})
  .catch(function(e){error=e.message;bonds=[];scores={};loading=!1;render();});
}
BE.fetchData = fetchData;

function sortedList(){var list=bonds.slice();
  if(search){var q=search.toLowerCase();list=list.filter(function(b){return(b.name&&b.name.toLowerCase().indexOf(q)>=0)||(b.internal_id&&b.internal_id.toLowerCase().indexOf(q)>=0)||(b.issuer&&b.issuer.toLowerCase().indexOf(q)>=0);});}
  list.sort(function(a,b){
    var av,bv;
    switch(sortKey){case'score':av=scores[a.internal_id]?scores[a.internal_id].score:-999;bv=scores[b.internal_id]?scores[b.internal_id].score:-999;break;case'ytm':av=Number(a.yield_to_maturity||-999);bv=Number(b.yield_to_maturity||-999);break;case'maturity':av=a.maturity_date?new Date(a.maturity_date).getTime():0;bv=b.maturity_date?new Date(b.maturity_date).getTime():0;break;default:av=0;bv=0;}
    var d=bv-av;return sortDir==='desc'?d:-d;
  });
  return list;}

BE.setSearch = function(v){search=v;page=0;render();};
BE.setCurrency = function(v){currency=v;page=0;fetchData();};
BE.prevPage = function(){if(page>0){page--;render();}};
BE.nextPage = function(){var tp=Math.max(1,Math.ceil(sortedList().length/PS));if(page<tp-1){page++;render();}};
BE.toggleSort = function(key){if(sortKey===key)sortDir=sortDir==='desc'?'asc':'desc';else{sortKey=key;sortDir='desc';}page=0;render();};
function sortIcon(key){return sortKey===key?(sortDir==='desc'?' \u2193':' \u2191'):' \u2195';}

var bondCache={};
BE.getBond = function(id){return bondCache[id];};

BE.openBond = function(bond){
  var s=scores[bond.internal_id];var bd=s?s.breakdown:null;var days=DAYS(bond.maturity_date);var factors='';
  if(bd){for(var k in FL){if(!FL.hasOwnProperty(k))continue;var v=Number(bd[k]||0);var cls=v>0?'be-f-pos':v<0?'be-f-neg':'be-f-neu';factors+='<div class="be-factor"><span>'+FL[k]+'</span><span class="'+cls+'">'+(v>0?'+':'')+v.toFixed(1)+'</span></div>';}}
  document.getElementById('be-modal').innerHTML='<div class="be-modal" onclick="event.stopPropagation()">'+
    '<div class="be-modal-hdr"><div><h3>'+T(bond.name,bond.internal_id)+'</h3>'+
    '<div style="font-size:12px;color:var(--tx-s);font-family:monospace">'+T(bond.internal_id)+(bond.issuer?' \u00b7 '+bond.issuer:'')+'</div></div>'+
    '<button class="be-btn be-btn-o" style="height:30px;width:30px;padding:0;min-width:30px" onclick="BE.closeModal()">\u2715</button></div>'+
    (s?'<div class="be-score-box"><div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">'+
    '<span class="be-tier '+(TIER_MAP[s.tier]||'t-B')+'" style="min-width:44px;height:32px;font-size:18px">'+(s.tier||'--')+'</span>'+
    '<div><div class="be-verdict '+(VCLS[s.tier]||'v-B')+'">'+(VERDICT[s.tier]||'')+'</div>'+
    '<div style="font-size:13px;color:var(--tx-s)">Reward/Risk Score: <strong>'+Number(s.score).toFixed(1)+'</strong> / 100</div></div></div>'+
    '<div class="be-factors">'+factors+'</div></div>':'')+
    '<div class="be-metrics">'+
    '<div><div class="be-ml">Рынок</div><div class="be-mv" style="color:'+marketColor+';font-weight:700">'+marketLabel+'</div></div>'+
    '<div><div class="be-ml">Валюта</div><div class="be-mv"><span class="be-cur">'+T(bond.currency)+'</span></div></div>'+
    '<div><div class="be-ml">Статус</div><div class="be-mv">'+T(bond.status)+'</div></div>'+
    '<div><div class="be-ml">Доходность</div><div class="be-mv" style="font-weight:700">'+FP(bond.yield_to_maturity)+'</div></div>'+
    '<div><div class="be-ml">Купон</div><div class="be-mv">'+FP(bond.coupon_rate)+'</div></div>'+
    '<div><div class="be-ml">Цена</div><div class="be-mv">'+(bond.price!=null?Number(bond.price).toFixed(2):'--')+'</div></div>'+
    '<div><div class="be-ml">Номинал</div><div class="be-mv">'+(bond.nominal!=null?Number(bond.nominal).toFixed(2):'--')+'</div></div>'+
    '<div><div class="be-ml">Погашение</div><div class="be-mv">'+FD(bond.maturity_date)+'</div></div>'+
    '<div><div class="be-ml">Дней</div><div class="be-mv" style="color:'+(days!=null&&days<365?'var(--wn-600)':'var(--tx-s)')+'">'+(days!=null?days+' дн':'--')+'</div></div>'+
    (bond.issuer?'<div style="grid-column:1/-1"><div class="be-ml">Эмитент</div><div class="be-mv">'+bond.issuer+'</div></div>':'')+
    '</div>'+
    '<div class="be-disc">Данная информация справочно-аналитическая. НЕ является индивидуальной инвестиционной рекомендацией.</div>'+
    '</div>';
  document.getElementById('be-modal').style.display='flex';};

BE.closeModal = function(){document.getElementById('be-modal').style.display='none';};

function render(){
  var list=sortedList(),tp=Math.max(1,Math.ceil(list.length/PS));
  if(page>=tp)page=Math.max(0,tp-1);
  var pg=list.slice(page*PS,(page+1)*PS);
  bondCache={};bonds.forEach(function(b){bondCache[b.internal_id]=b;});
  var cc={};CURS.filter(function(c){return c.k;}).forEach(function(c){cc[c.k]=bonds.filter(function(b){return String(b.currency||'').toUpperCase()===c.k;}).length;});
  var h='<div class="be-hdr"><h2>Аналитика облигаций</h2><span style="color:'+marketColor+';font-weight:600">\u25CF '+marketLabel+'</span><span>'+bonds.length+' выпусков \u00b7 Score v3</span></div>';
  if(error)h+='<div class="be-err">'+error+' <button class="be-btn be-btn-o be-btn-sm" onclick="BE.fetchData()">\u041f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u044c</button></div>';
  else if(loading)h+='<div class="be-load"><div class="be-spin"></div>\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430...</div>';
  else {
    h+='<div class="be-toolbar"><input class="be-inp" type="text" placeholder="\u041f\u043e\u0438\u0441\u043a \u043f\u043e \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u044e, ISIN, \u044d\u043c\u0438\u0442\u0435\u043d\u0442\u0443..." value="'+search.replace(/"/g,'&quot;')+'" oninput="BE.setSearch(this.value)">';
    CURS.forEach(function(c){h+='<button class="be-btn '+(currency===c.k?'be-btn-p active':'be-btn-o')+' be-btn-sm" onclick="BE.setCurrency(\''+c.k+'\')">'+c.l+(c.k&&cc[c.k]!==undefined?' <span style="opacity:.6">'+cc[c.k]+'</span>':'')+'</button>';});
    h+='</div>';
    if(list.length===0)h+='<div class="be-empty">\u041e\u0431\u043b\u0438\u0433\u0430\u0446\u0438\u0439 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e</div>';
    else {
      h+='<table class="be-tbl"><thead><tr>'+
        '<th onclick="BE.toggleSort(\'name\')">\u041e\u0431\u043b\u0438\u0433\u0430\u0446\u0438\u044f'+sortIcon('name')+'</th>'+
        '<th onclick="BE.toggleSort(\'score\')">\u0421\u043a\u043e\u0440'+sortIcon('score')+'</th>'+
        '<th onclick="BE.toggleSort(\'ytm\')">YTM'+sortIcon('ytm')+'</th>'+
        '<th>\u041a\u0443\u043f\u043e\u043d</th><th>\u0412\u0430\u043b\u044e\u0442\u0430</th>'+
        '<th onclick="BE.toggleSort(\'maturity\')">\u041f\u043e\u0433\u0430\u0448\u0435\u043d\u0438\u0435'+sortIcon('maturity')+'</th>'+
        '<th>\u0414\u043d\u0435\u0439</th></tr></thead><tbody>';
      pg.forEach(function(b){
        var s=scores[b.internal_id];var days=DAYS(b.maturity_date);var ytm=Number(b.yield_to_maturity||0);
        h+='<tr onclick="BE.openBond(BE.getBond(\''+b.internal_id+'\'))" title="'+MARKET.toUpperCase()+' \u00b7 '+T(b.currency)+'">'+
          '<td><div style="font-weight:600;font-size:13px">'+T(b.name,b.internal_id)+'</div><div style="font-size:11px;color:var(--tx-s)">'+T(b.issuer,'')+'</div></td>'+
          '<td>'+(s?'<span style="display:flex;align-items:center;gap:8px"><span class="be-tier '+(TIER_MAP[s.tier]||'t-B')+'">'+(s.tier||'--')+'</span><span style="font-weight:600;font-size:14px">'+Number(s.score).toFixed(1)+'</span></span>':'<span style="color:var(--tx-d)">--</span>')+'</td>'+
          '<td><span class="'+(ytm>=10?'be-ytm-g':ytm>=5?'be-ytm-m':'be-ytm-l')+'">'+FP(b.yield_to_maturity)+'</span></td>'+
          '<td style="font-weight:600">'+FP(b.coupon_rate)+'</td>'+
          '<td><span class="be-cur">'+T(b.currency)+'</span></td>'+
          '<td style="font-size:12px">'+FD(b.maturity_date)+'</td>'+
          '<td style="font-size:12px;color:'+(days!=null&&days<365?'var(--wn-600)':'var(--tx-s)')+'">'+(days!=null?days+' \u0434\u043d':'--')+'</td></tr>';
      });
      h+='</tbody></table>';
      if(tp>1)h+='<div class="be-pag"><button class="be-btn be-btn-o be-btn-sm" '+(page===0?'disabled':'onclick="BE.prevPage()"')+'>\u2190 \u041d\u0430\u0437\u0430\u0434</button><span>'+(page+1)+' / '+tp+'</span><button class="be-btn be-btn-o be-btn-sm" '+(page>=tp-1?'disabled':'onclick="BE.nextPage()"')+'>\u0412\u043f\u0435\u0440\u0451\u0434 \u2192</button></div>';
    }
  }
  document.getElementById('be-app').innerHTML=h;
}
BE.render = render;

})();

/* Places to Eat page. Progressive enhancement: the page is complete without JS. */
(function(){
var d=document,q=function(s,r){return Array.prototype.slice.call((r||d).querySelectorAll(s))};
var list=d.querySelector('.rs-list'); if(!list) return;
var cards=q('.rs',list), DAYS=['mon','tue','wed','thu','fri','sat','sun'];
var tools=d.querySelector('.rs-tools'); tools.hidden=false;
function nowNY(){
  var p=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',weekday:'short',hour:'numeric',minute:'numeric',hour12:false,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date()),o={};
  p.forEach(function(x){o[x.type]=x.value});
  var wd=['mon','tue','wed','thu','fri','sat','sun'].indexOf(o.weekday.slice(0,3).toLowerCase());
  return {day:wd,min:(+o.hour%24)*60+(+o.minute),date:o.year+'-'+o.month+'-'+o.day};
}
function mins(t){var a=t.split(':');return +a[0]*60+ +a[1]}
function fmt(t){var a=t.split(':'),h=+a[0],m=a[1],s=h>=12?'p.m.':'a.m.';h=h%12||12;return h+(m==='00'?'':':'+m)+' '+s}
function rng(r){return fmt(r[0])+' to '+fmt(r[1])}
function state(c,n){
  var st=c.dataset.status,h=JSON.parse(c.dataset.hours),re=c.dataset.reopens||'';
  if(st==='closed_for_season') return {k:'closed',t:'Closed for the season'+(re?' (back '+re+')':'')};
  if(st==='preorder_only') return {k:'unknown',t:'Pre-order only right now'};
  if(st==='temporarily_closed'&&/^\d{4}-/.test(re)&&n.date<re) return {k:'closed',t:'Closed for a break until '+c.dataset.reopensText};
  var td=h[DAYS[n.day]];
  if(td===null||td===undefined) return {k:'unknown',t:'Hours not confirmed, call ahead'};
  if(!td.length) return {k:'closed',t:'Closed today'};
  for(var i=0;i<td.length;i++){var a=mins(td[i][0]),b=mins(td[i][1]);
    if(n.min>=a&&n.min<b) return {k:'open',t:'Open now, until '+fmt(td[i][1]),open:true};}
  for(i=0;i<td.length;i++){if(n.min<mins(td[i][0])) return {k:'closed',t:'Closed now, opens at '+fmt(td[i][0])};}
  return {k:'closed',t:'Closed now'};
}
function today(c,n){
  var h=JSON.parse(c.dataset.hours),td=h[DAYS[n.day]];
  if(td===null||td===undefined) return '';
  return td.length?'Today: '+td.map(rng).join(', '):'Closed today';
}
var nOpen=null;
function paint(){
  var n=nowNY();
  cards.forEach(function(c){
    var s=state(c,n), b=c.querySelector('.rs-state');
    b.className='rs-badge rs-state rs-b-'+(s.k==='open'?'open':s.k==='closed'?'closed':'unknown'); b.textContent=s.t;
    c.dataset.now=s.open?'open':'no'; c.classList.toggle('is-closed',s.k==='closed');
    var t=c.querySelector('.rs-today'); if(t&&c.dataset.status==='open') t.textContent=today(c,n);
    q('tr',c).forEach(function(r){r.classList.toggle('is-today',r.dataset.d===DAYS[n.day])});
  });
}
var cat='all',openOnly=false,term='';
var chips=q('[data-f]',tools),ob=d.getElementById('rs-open'),sb=d.getElementById('rs-q'),cnt=d.getElementById('rs-count');
function apply(){
  var shown=0,lab=cat==='all'?'':d.querySelector('[data-f="'+cat+'"]').dataset.label.toLowerCase();
  cards.forEach(function(c){
    var ok=(cat==='all'||c.dataset.cats.split(' ').indexOf(cat)>-1)&&(!openOnly||c.dataset.now==='open')&&(!term||c.dataset.search.indexOf(term)>-1);
    c.hidden=!ok; if(ok) shown++;
  });
  chips.forEach(function(x){x.setAttribute('aria-pressed',x.dataset.f===cat)});
  ob.setAttribute('aria-pressed',openOnly);
  var m=d.getElementById('rs-none'); m.hidden=shown>0;
  cnt.textContent=shown+' '+(shown===1?'place':'places')+(lab?' ('+lab+')':'')+(openOnly?' open now':'');
  var u=new URL(location.href); cat==='all'?u.searchParams.delete('type'):u.searchParams.set('type',cat); history.replaceState(null,'',u);
}
chips.forEach(function(x){x.addEventListener('click',function(){cat=x.dataset.f;apply()})});
ob.addEventListener('click',function(){openOnly=!openOnly;apply()});
sb.addEventListener('input',function(){term=sb.value.trim().toLowerCase();apply()});
var t=new URLSearchParams(location.search).get('type'); if(t&&d.querySelector('[data-f="'+t+'"]')) cat=t;
paint(); apply(); setInterval(function(){paint();apply()},60000);
})();

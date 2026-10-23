/* events-component v1.0 2026-10 */
(function(){var d=document,r=d.documentElement,q=function(s,c){return[].slice.call((c||d).querySelectorAll(s))},nav=d.querySelector("header.nav"),bar=d.querySelector(".ev-bar");
function sz(){nav&&r.style.setProperty("--ev-top",nav.offsetHeight+"px");bar&&r.style.setProperty("--ev-bar",bar.offsetHeight+"px")}sz();addEventListener("resize",sz);
var n=new Date(),t=n.getFullYear()+"-"+("0"+(n.getMonth()+1)).slice(-2)+"-"+("0"+n.getDate()).slice(-2);
q(".ev[data-end]").forEach(function(e){e.dataset.end<t&&(e.hidden=!0)});
var f=d.querySelector(".ev-filters"),o=d.getElementById("ev-count");if(!f)return;f.hidden=!1;
var b=q("[data-f]",f);function ap(k,u){var lb=k=="all"?"":d.querySelector('[data-f="'+k+'"]').textContent,tot=0;
b.forEach(function(x){x.setAttribute("aria-pressed",x.dataset.f==k)});
q(".ev-month").forEach(function(s){var c=0;q(".ev,.ev-still span",s).forEach(function(e){var on=k=="all"||e.dataset.cat==k;e.classList.toggle("ev-f-off",!on);on&&!e.hidden&&e.tagName=="LI"&&c++});
tot+=c;var st=s.querySelector(".ev-still"),sv=st&&q("span:not(.ev-f-off)",st).length;st&&(st.hidden=!sv);
var m=s.querySelector(".ev-nomatch"),em=s.querySelector(".ev-empty");m.hidden=k=="all"||c>0||!!em;m.textContent="No "+lb+" events this month.";
var ch=d.querySelector('[data-m="'+s.id+'"]');if(ch){ch.querySelector(".ev-n").textContent=c;ch.classList.toggle("ev-zero",!c)}});
o.textContent="Showing "+tot+" "+(lb?lb+" ":"")+"events";
if(u&&history.replaceState){var p=new URL(location);k=="all"?p.searchParams.delete("type"):p.searchParams.set("type",k);history.replaceState(null,"",p)}}
b.forEach(function(x){x.onclick=function(){ap(x.dataset.f,1)}});
var k=new URLSearchParams(location.search).get("type");k&&d.querySelector('[data-f="'+k+'"]')&&ap(k);
if("IntersectionObserver"in window){var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){q(".ev-mchip").forEach(function(c){c.dataset.m==e.target.id?c.setAttribute("aria-current","true"):c.removeAttribute("aria-current")})}})},{rootMargin:"-30% 0px -60% 0px"});q(".ev-month").forEach(function(s){io.observe(s)})}})();

/* theme.js — BeerSniffer designlag: ordmærke + overskrift i toppen og "Dagens fund".
   Ændrer kun visningen; alle elementer, som sidens eget script bruger (id'er), bevares. Fejler stille. */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var txt = function (s) { var e = $(s); return e ? e.textContent.trim() : ''; };

  /* 1) top: ordmærke, overskrift og undertekst ved siden af hunden */
  function initHeader() {
    var brand = $('.brand');
    if (!brand || $('.bm-title', brand)) return;
    var eb = document.createElement('div'); eb.className = 'bm-eyebrow'; eb.textContent = 'BeerSniffer';
    var h = document.createElement('h2'); h.className = 'bm-title'; h.innerHTML = 'Samme øl. <span class="bm-br"></span><em>Laveste pris.</em>';
    var sub = document.createElement('p'); sub.className = 'bm-sub'; sub.id = 'bm-sub';
    brand.insertBefore(sub, brand.firstChild); brand.insertBefore(h, brand.firstChild); brand.insertBefore(eb, brand.firstChild);
    fillSub();
    ['#hero-beer-count', '#brand-shop-count'].forEach(function (s) {
      var e = $(s); if (e) new MutationObserver(fillSub).observe(e, { childList: true, characterData: true, subtree: true });
    });
  }
  function fillSub() {
    var sub = $('#bm-sub'); if (!sub) return;
    var n = txt('#hero-beer-count'), s = txt('#brand-shop-count');
    var html = 'Sammenlign <strong>' + (n || 'tusindvis af') + '</strong> øl fra <strong>' + (s || 'flere') + '</strong> danske webshops — opdateres dagligt';
    if (sub.innerHTML !== html) sub.innerHTML = html;        // kun ved ændring (undgår løkker)
  }

  /* 2) Dagens fund: tilbudsstrimlens første kort løftes op som ét redaktionelt kort */
  function syncFund() {
    var scroll = $('#top-deals-scroll'), sec = $('#top-deals-section');
    if (!scroll || !sec) return;
    var fund = $('#bm-fund');
    if (fund) {                                              // fjern dubletten, hvis strimlen genopbygges
      var href = fund.getAttribute('data-href');
      Array.prototype.forEach.call(scroll.querySelectorAll('.top-card'), function (c) { if (c.getAttribute('data-href') === href) c.remove(); });
      return;
    }
    var tc = $('.top-card', scroll); if (!tc) return;
    var g = function (s) { var e = $(s, tc); return e ? e.textContent.trim() : ''; };
    var img = $('img', tc), link = $('.top-card-link', tc);
    var f = document.createElement('section'); f.className = 'bm-fund'; f.id = 'bm-fund';
    f.setAttribute('data-href', tc.getAttribute('data-href') || '');
    f.setAttribute('aria-label', 'Dagens fund');
    f.innerHTML =
      '<div class="bm-fund-inner"><div class="bm-fund-head"><span class="bm-fund-title">Dagens fund</span><span class="bm-fund-sub">Største rabat lige nu</span></div>' +
      '<div class="bm-fund-card"><div class="bm-fund-photo"></div><div class="bm-fund-info"><div class="bm-fund-brew"></div><div class="bm-fund-name"></div>' +
      '<div class="bm-fund-prices"><span class="bm-fund-price"></span><span class="bm-fund-old"></span><span class="bm-fund-pct"></span></div></div></div></div>';
    $('.bm-fund-brew', f).textContent = g('.top-card-shop');
    $('.bm-fund-name', f).textContent = g('.top-card-name');
    $('.bm-fund-price', f).textContent = g('.top-card-price');
    var old = g('.top-card-old'); if (old) $('.bm-fund-old', f).textContent = old; else $('.bm-fund-old', f).remove();
    $('.bm-fund-pct', f).textContent = g('.top-card-pct').replace('−', '-');
    if (img) { var im = document.createElement('img'); im.src = img.currentSrc || img.src; im.alt = ''; $('.bm-fund-photo', f).appendChild(im); }
    if (link) { var a = link.cloneNode(true); a.className = 'bm-fund-cta'; a.setAttribute('data-place', 'dagens_fund'); a.textContent = 'Køb →'; $('.bm-fund-card', f).appendChild(a); }
    sec.parentNode.insertBefore(f, sec);
    var t = $('.top-deals-title', sec);
    if (t && t.lastChild && t.lastChild.nodeType === 3) t.lastChild.textContent = 'Flere tilbud';
    tc.remove();
  }

  function start() {
    try { initHeader(); } catch (e) {}
    var scroll = $('#top-deals-scroll');
    if (scroll) { new MutationObserver(function () { try { syncFund(); } catch (e) {} }).observe(scroll, { childList: true }); try { syncFund(); } catch (e) {} }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();

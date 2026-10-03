(function () {
  var B = "/Redsea-monitor/";
  var items = [
    ["redsea/", "Rudé moře"],
    ["usa/", "USA"],
    ["europe/", "Evropa"],
    ["middle-east/", "Blízký východ"],
    ["asia/", "Čína a Asie"],
    ["japan/", "Japonsko"],
    ["czechia/", "Česko"],
    ["hledani/", "Hledání"],
    ["uspesnost/", "Úspěšnost"],
    ["navstevnost/", "Návštěvnost"]
  ];
  var path = location.pathname.replace(/index\.html$/, "");
  var linkCss = "flex:none;color:var(--brass,#b8863b);text-decoration:none;" +
    "border:1px solid var(--rule,rgba(184,134,59,.35));padding:4px 10px;border-radius:2px";
  var html = '<a href="' + B + '" style="' + linkCss + ';font-weight:600' +
    (path === B ? ";background:rgba(184,134,59,.18)" : "") + '">☰ Přehled</a>';
  items.forEach(function (it) {
    var href = B + it[0];
    var on = path === href;
    html += '<a href="' + href + '" style="' + linkCss +
      (on ? ";background:rgba(184,134,59,.18);font-weight:600" : "") + '">' + it[1] + "</a>";
  });
  var bar = document.createElement("nav");
  bar.setAttribute("aria-label", "Monitory");
  bar.style.cssText =
    "display:flex;gap:6px;overflow-x:auto;white-space:nowrap;padding:8px 12px;" +
    "background:var(--ink2,#142c3a);border-bottom:1px solid var(--rule,rgba(184,134,59,.35));" +
    "font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.03em";
  bar.innerHTML = html;
  document.body.insertBefore(bar, document.body.firstChild);

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register(B + "sw.js", { scope: B }).catch(function () {});
  }
})();

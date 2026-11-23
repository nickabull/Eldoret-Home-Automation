/* Eldoret unified navigation: every device page returns to Nerd Central.
   Deliberately navigation-only: no device commands, no background polling. */
(()=>{"use strict";
if(document.getElementById("eldoretNerdHome")||/\/ipad11\.html$/.test(location.pathname))return;
const a=document.createElement("a");
a.id="eldoretNerdHome";
a.href="/ipad11.html";
a.textContent="⌂  NERD CENTRAL";
a.setAttribute("aria-label","Home: return to Nerd Central");
a.style.cssText="position:fixed;left:max(12px,env(safe-area-inset-left));bottom:max(12px,env(safe-area-inset-bottom));z-index:2147483000;display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:11px 17px;border-radius:13px;border:1px solid #81d3be;background:#0b2638f2;color:#dffff4;text-decoration:none;font:800 12px Arial,Helvetica,sans-serif;letter-spacing:.07em;box-shadow:0 4px 18px #000b;backdrop-filter:blur(8px)";
document.body.appendChild(a);
})();
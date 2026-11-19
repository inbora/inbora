/* Inbora website chat.
   Add to a site with:
   <script src="https://YOUR-API/widget/widget.js" data-key="wk_..." async></script> */
(function () {
  "use strict";
  if (window.__inboraChat) return;
  window.__inboraChat = true;

  var script = document.currentScript ||
    document.querySelector('script[src*="/widget/widget.js"][data-key]');
  if (!script) return;
  var KEY = script.getAttribute("data-key");
  var API = new URL(script.src, location.href).origin;
  if (!KEY) return;

  var T = {
    en: { placeholder: "Write a message…", send: "Send", open: "Open chat", close: "Close chat",
          team: "Team", today: "Today", yesterday: "Yesterday", powered: "Powered by",
          error: "The message didn't go through. Please try again.", busy: "You're sending messages too quickly. Please wait a moment.",
          subtitle: "We're here to help", teamOn: "A team member is with you",
          attach: "Attach a photo", remove: "Remove photo", tooBig: "Photos can be up to 5 MB.", badType: "Only photos (JPG, PNG, WEBP, GIF) can be sent." },
    he: { placeholder: "כתבו הודעה…", send: "שליחה", open: "פתיחת צ׳אט", close: "סגירת הצ׳אט",
          team: "צוות", today: "היום", yesterday: "אתמול", powered: "מופעל על ידי",
          error: "ההודעה לא נשלחה. נסו שוב.", busy: "שלחתם הרבה הודעות ברצף. חכו רגע ונסו שוב.",
          subtitle: "כאן כדי לעזור", teamOn: "נציג מהצוות איתכם",
          attach: "צירוף תמונה", remove: "הסרת התמונה", tooBig: "תמונות עד 5MB.", badType: "אפשר לשלוח רק תמונות (JPG, PNG, WEBP, GIF)." },
    ar: { placeholder: "اكتب رسالة…", send: "إرسال", open: "فتح الدردشة", close: "إغلاق الدردشة",
          team: "الفريق", today: "اليوم", yesterday: "أمس", powered: "مدعوم من",
          error: "لم تُرسل الرسالة. حاول مرة أخرى.", busy: "أرسلت رسائل كثيرة بسرعة. انتظر لحظة من فضلك.",
          subtitle: "نحن هنا للمساعدة", teamOn: "أحد أعضاء الفريق معك",
          attach: "إرفاق صورة", remove: "إزالة الصورة", tooBig: "الصور حتى 5 ميغابايت.", badType: "يمكن إرسال الصور فقط (JPG وPNG وWEBP وGIF)." }
  };

  function store(k, v) {
    try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; }
  }
  var vid = store("inbora_v_" + KEY);
  if (!vid || !/^v_[A-Za-z0-9]{16,48}$/.test(vid)) {
    var a = new Uint8Array(16), chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    (window.crypto || window.msCrypto).getRandomValues(a);
    vid = "v_" + Array.prototype.map.call(a, function (b) { return chars[b % 62] + chars[(b * 7) % 62]; }).join("");
    store("inbora_v_" + KEY, vid);
  }

  function req(method, path, body) {
    var opts = { method: method };
    if (body) {
      // text/plain keeps this a "simple" request: no CORS preflight.
      opts.headers = { "Content-Type": "text/plain;charset=UTF-8" };
      opts.body = JSON.stringify(body);
    }
    return fetch(API + "/widget/" + encodeURIComponent(KEY) + path, opts).then(function (r) {
      if (!r.ok) { var e = new Error("HTTP " + r.status); e.status = r.status; throw e; }
      return r.json();
    });
  }

  function textOn(hex) {
    var n = parseInt(hex.slice(1), 16), r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
    var lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
    return lum > 0.6 ? "#14161a" : "#ffffff";
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function anchor(url, label) {
    return '<a href="' + url + '" target="_blank" rel="noopener noreferrer nofollow" dir="ltr">' + (label || url) + "</a>";
  }
  // Escape first, then turn [label](url) and bare URLs into links.
  function linkify(text) {
    var s = esc(text);
    s = s.replace(/\[([^\]]*)\]\((https?:\/\/[^\s()<>\[\]"']+)\)/g, function (_m, label, url) {
      return anchor(url, label.trim() || url);
    });
    s = s.replace(/(^|[^"'>=])(https?:\/\/[^\s()<>\[\]"']+)/g, function (_m, pre, url) {
      var trail = "", t = url.match(/[.,;:!?–—]+$/);
      if (t) { trail = t[0]; url = url.slice(0, -trail.length); }
      return pre + anchor(url) + trail;
    });
    return s;
  }

  req("GET", "/config").then(start).catch(function () { /* chat switched off or unknown key */ });

  function start(cfg) {
    var pageLang = (document.documentElement.lang || "").slice(0, 2).toLowerCase();
    var lang = T[pageLang] ? pageLang : (T[cfg.language] ? cfg.language : "en");
    var t = T[lang], rtl = lang === "he" || lang === "ar";
    var color = /^#[0-9a-fA-F]{6}$/.test(cfg.color || "") ? cfg.color : "#0e9f6e";
    var side = cfg.position === "left" ? "left" : "right";

    var host = document.createElement("div");
    host.setAttribute("data-inbora", "");
    host.style.cssText = "position:fixed;z-index:2147483000;bottom:0;" + side + ":0;";
    document.body.appendChild(host);
    var root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;

    root.innerHTML =
      "<style>" +
      ":host{all:initial}" +
      "*{box-sizing:border-box;font-family:system-ui,-apple-system,'Segoe UI',Roboto,Arial,'Noto Sans Hebrew','Noto Sans Arabic',sans-serif}" +
      ".btn{position:fixed;bottom:20px;" + side + ":20px;width:58px;height:58px;border-radius:50%;border:0;cursor:pointer;background:" + color + ";color:" + textOn(color) + ";box-shadow:0 6px 24px rgba(0,0,0,.22);display:flex;align-items:center;justify-content:center;transition:transform .15s}" +
      ".btn:hover{transform:scale(1.06)}.btn svg{width:28px;height:28px;fill:currentColor}" +
      ".dot{position:absolute;top:6px;" + (side === "right" ? "right" : "left") + ":6px;width:12px;height:12px;border-radius:50%;background:#e02424;border:2px solid #fff;display:none}" +
      ".dot.on{display:block}" +
      ".panel{position:fixed;bottom:90px;" + side + ":20px;width:370px;max-width:calc(100vw - 24px);height:560px;max-height:calc(100vh - 110px);background:#fff;border-radius:16px;box-shadow:0 16px 48px rgba(0,0,0,.24);display:none;flex-direction:column;overflow:hidden;color:#14161a;font-size:14px}" +
      ".panel.open{display:flex}" +
      ".head{background:" + color + ";color:" + textOn(color) + ";padding:14px 16px;display:flex;align-items:center;gap:10px}" +
      ".head .who{flex:1;min-width:0}.head .name{font-weight:700;font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
      ".head .sub{font-size:12px;opacity:.85;margin-top:2px}" +
      ".x{background:none;border:0;color:inherit;font-size:24px;line-height:1;cursor:pointer;padding:2px 6px;opacity:.85}.x:hover{opacity:1}" +
      ".list{flex:1;overflow-y:auto;padding:14px;background:#f6f7f9;display:flex;flex-direction:column;gap:8px}" +
      ".m{max-width:82%;padding:9px 13px;border-radius:14px;line-height:1.5;white-space:pre-wrap;word-wrap:break-word;overflow-wrap:anywhere}" +
      ".m.user{align-self:flex-end;background:" + color + ";color:" + textOn(color) + ";border-end-end-radius:4px}" +
      ".m.bot,.m.human{align-self:flex-start;background:#fff;border:1px solid #e3e6ea;border-end-start-radius:4px}" +
      ".m.human{border-color:" + color + "}" +
      ".m .tag{display:block;font-size:11px;font-weight:700;color:" + color + ";margin-bottom:2px}" +
      ".m .img{display:block;max-width:100%;max-height:220px;border-radius:8px;margin:2px 0 4px}" +
      ".m a{color:inherit;text-decoration:underline}.m .time{display:block;font-size:10px;opacity:.55;margin-top:3px}" +
      ".sep{align-self:center;background:#e7e9ed;color:#5d6470;font-size:11px;padding:2px 10px;border-radius:10px;margin:4px 0}" +
      ".typing{align-self:flex-start;background:#fff;border:1px solid #e3e6ea;border-radius:14px;padding:12px 14px;display:none;gap:4px}" +
      ".typing.on{display:flex}.typing i{width:6px;height:6px;border-radius:50%;background:#9aa1ab;animation:b 1.2s infinite}" +
      ".typing i:nth-child(2){animation-delay:.15s}.typing i:nth-child(3){animation-delay:.3s}" +
      "@keyframes b{0%,60%,100%{transform:translateY(0);opacity:.5}30%{transform:translateY(-4px);opacity:1}}" +
      ".err{align-self:center;color:#b42318;font-size:12px;text-align:center}" +
      ".bar{display:flex;gap:8px;padding:10px;border-top:1px solid #eceef1;background:#fff;align-items:flex-end}" +
      ".clip{flex-shrink:0;width:38px;height:42px;border:0;background:none;cursor:pointer;color:#8a919b;display:flex;align-items:center;justify-content:center;border-radius:50%}" +
      ".clip:hover{color:" + color + "}.clip svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}" +
      ".pv{display:none;padding:8px 12px 0;background:#fff}.pv.on{display:block}.pv .th{position:relative;display:inline-block}" +
      ".pv img{max-height:64px;border-radius:8px;border:1px solid #e3e6ea;display:block}" +
      ".pv .rm{position:absolute;top:-7px;" + (rtl ? "left" : "right") + ":-7px;width:20px;height:20px;border-radius:50%;border:0;background:#14161a;color:#fff;font-size:13px;line-height:1;cursor:pointer}" +
      "textarea{flex:1;min-width:0;resize:none;border:1px solid #d5d9df;border-radius:20px;padding:10px 14px;font-size:16px;line-height:1.35;max-height:120px;outline:none;color:#14161a;background:#fff}" +
      "textarea:focus{border-color:" + color + "}" +
      ".send{flex-shrink:0;width:42px;height:42px;border-radius:50%;border:0;cursor:pointer;background:" + color + ";color:" + textOn(color) + ";display:flex;align-items:center;justify-content:center}" +
      ".send:disabled{opacity:.5;cursor:default}.send svg{width:20px;height:20px;fill:currentColor" + (rtl ? ";transform:scaleX(-1)" : "") + "}" +
      ".brand{text-align:center;font-size:11px;color:#8a919b;padding:0 0 8px;background:#fff}.brand a{color:#5d6470;font-weight:600;text-decoration:none}" +
      "@media (max-width:480px){.panel{bottom:0;" + side + ":0;width:100vw;max-width:100vw;height:100%;max-height:100%;border-radius:0}.panel.open~.btn{display:none}}" +
      "</style>" +
      '<div class="panel" role="dialog" dir="' + (rtl ? "rtl" : "ltr") + '" lang="' + lang + '">' +
      '<div class="head"><div class="who"><div class="name"></div><div class="sub"></div></div>' +
      '<button class="x" aria-label="' + esc(t.close) + '">&times;</button></div>' +
      '<div class="list" aria-live="polite"><div class="typing"><i></i><i></i><i></i></div></div>' +
      '<div class="pv"></div>' +
      '<div class="bar"><input class="file" type="file" accept="image/jpeg,image/png,image/webp,image/gif" hidden>' +
      '<button class="clip" aria-label="' + esc(t.attach) + '" title="' + esc(t.attach) + '"><svg viewBox="0 0 24 24"><path d="M21 11.5l-8.6 8.6a5 5 0 0 1-7.1-7.1l8.6-8.6a3.3 3.3 0 0 1 4.7 4.7l-8.6 8.6a1.7 1.7 0 0 1-2.4-2.4l7.9-7.9"/></svg></button>' +
      '<textarea rows="1" maxlength="2000" placeholder="' + esc(t.placeholder) + '"></textarea>' +
      '<button class="send" aria-label="' + esc(t.send) + '"><svg viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2v7z"/></svg></button></div>' +
      (cfg.branding ? '<div class="brand">' + esc(t.powered) + ' <a href="https://inbora.ai" target="_blank" rel="noopener">Inbora</a></div>' : "") +
      "</div>" +
      '<button class="btn" aria-label="' + esc(t.open) + '"><svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.04 2 11c0 2.7 1.34 5.11 3.46 6.74L4.5 22l4.78-2.04c.86.2 1.77.31 2.72.31 5.52 0 10-4.04 10-9S17.52 2 12 2z"/></svg><span class="dot"></span></button>';

    var $ = function (s) { return root.querySelector(s); };
    var panel = $(".panel"), list = $(".list"), typing = $(".typing"), input = $("textarea"),
        sendBtn = $(".send"), btn = $(".btn"), dot = $(".dot"), sub = $(".sub");
    $(".name").textContent = cfg.name || "";
    sub.textContent = t.subtitle;

    var shown = {}, lastId = 0, lastDay = null, loaded = false, waiting = false, timer = null;
    var started = store("inbora_s_" + KEY) === "1";

    function dayKey(ts) { var d = new Date(ts); return d.getFullYear() + "-" + d.getMonth() + "-" + d.getDate(); }
    function dayLabel(ts) {
      var k = dayKey(ts);
      if (k === dayKey(Date.now())) return t.today;
      if (k === dayKey(Date.now() - 864e5)) return t.yesterday;
      return new Date(ts).toLocaleDateString(lang);
    }
    function clock(ts) {
      try { return new Date(ts).toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" }); } catch (e) { return ""; }
    }
    function add(role, text, ts, id, img) {
      if (id) { if (shown[id]) return; shown[id] = 1; if (id > lastId) lastId = id; }
      ts = ts || new Date().toISOString();
      if (dayKey(ts) !== lastDay) {
        lastDay = dayKey(ts);
        var sep = document.createElement("div"); sep.className = "sep"; sep.textContent = dayLabel(ts);
        list.insertBefore(sep, typing);
      }
      var d = document.createElement("div");
      d.className = "m " + (role === "user" ? "user" : role === "human" ? "human" : "bot");
      var html = "";
      if (role === "human") html += '<span class="tag">' + esc(t.team + " · " + (cfg.name || "")) + "</span>";
      if (img && /^(https:\/\/|data:image\/)/.test(img)) html += '<a href="' + esc(img) + '" target="_blank" rel="noopener"><img class="img" src="' + esc(img) + '" alt=""></a>';
      html += '<span dir="auto" style="display:block">' + linkify(text || "") + '</span><span class="time">' + esc(clock(ts)) + "</span>";
      d.innerHTML = html;
      list.insertBefore(d, typing);
      list.scrollTop = list.scrollHeight;
      return d;
    }
    function note(text) {
      var d = document.createElement("div"); d.className = "err"; d.textContent = text;
      list.insertBefore(d, typing); list.scrollTop = list.scrollHeight;
      setTimeout(function () { d.remove(); }, 8000);
    }
    function setTyping(on) {
      typing.classList.toggle("on", !!on);
      if (on) list.scrollTop = list.scrollHeight;
    }
    function apply(data) {
      var fresh = false;
      (data.messages || []).forEach(function (m) {
        if (!shown[m.id]) {
          var img = (m.attachment_mime || "").indexOf("image/") === 0 ? m.attachment_url : null;
          add(m.role, m.content, m.created_at, m.id, img);
          if (m.role !== "user") fresh = true;
        }
      });
      if (fresh) waiting = false;
      setTyping(data.typing || waiting);
      sub.textContent = data.team ? t.teamOn : t.subtitle;
      return fresh;
    }

    function schedule() {
      clearTimeout(timer);
      var open = panel.classList.contains("open");
      if (!open && !started) return;
      var ms = open ? (typing.classList.contains("on") ? 2000 : 5000) : 25000;
      if (document.hidden) ms = Math.max(ms, 30000);
      timer = setTimeout(poll, ms);
    }
    function poll() {
      req("GET", "/messages?visitor_id=" + vid + "&after=" + lastId).then(function (data) {
        var fresh = apply(data);
        if (fresh && !panel.classList.contains("open")) dot.classList.add("on");
      }).catch(function () {}).then(schedule);
    }
    function loadHistory() {
      req("GET", "/messages?visitor_id=" + vid).then(function (data) {
        if (!(data.messages || []).length && cfg.greeting) add("assistant", cfg.greeting);
        apply(data);
      }).catch(function () { if (cfg.greeting) add("assistant", cfg.greeting); }).then(schedule);
    }

    function open() {
      panel.classList.add("open"); dot.classList.remove("on");
      if (!loaded) { loaded = true; loadHistory(); } else { poll(); }
      if (!("ontouchstart" in window)) input.focus();
    }
    function close() { panel.classList.remove("open"); schedule(); }
    btn.addEventListener("click", function () { panel.classList.contains("open") ? close() : open(); });
    $(".x").addEventListener("click", close);

    function grow() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 120) + "px"; }
    input.addEventListener("input", grow);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
    });
    sendBtn.addEventListener("click", send);

    var fileIn = $(".file"), pv = $(".pv"), photo = null;
    $(".clip").addEventListener("click", function () { fileIn.click(); });
    function clearPhoto() { photo = null; pv.innerHTML = ""; pv.classList.remove("on"); }
    fileIn.addEventListener("change", function () {
      var f = fileIn.files && fileIn.files[0];
      fileIn.value = "";
      if (!f) return;
      if (!/^image\/(jpeg|png|webp|gif)$/.test(f.type)) { note(t.badType); return; }
      if (f.size > 5 * 1024 * 1024) { note(t.tooBig); return; }
      var r = new FileReader();
      r.onload = function () {
        var url = String(r.result);
        photo = { base64: url.split(",")[1] || "", mime: f.type, url: url };
        pv.innerHTML = '<span class="th"><img alt="" src="' + url + '"><button class="rm" aria-label="' + esc(t.remove) + '">&times;</button></span>';
        pv.classList.add("on");
        pv.querySelector(".rm").addEventListener("click", clearPhoto);
        if (!("ontouchstart" in window)) input.focus();
      };
      r.readAsDataURL(f);
    });

    function send() {
      var text = input.value.trim();
      if ((!text && !photo) || sendBtn.disabled) return;
      sendBtn.disabled = true;
      var sending = photo;
      var bubble = add("user", text, null, null, sending ? sending.url : null);
      input.value = ""; grow(); clearPhoto();
      var body = { visitor_id: vid, text: text, page: location.href.slice(0, 500) };
      if (sending) body.image = { base64: sending.base64, mime: sending.mime };
      req("POST", "/messages", body)
        .then(function (r) {
          shown[r.id] = 1; if (r.id > lastId) lastId = r.id;
          if (!started) { started = true; store("inbora_s_" + KEY, "1"); }
          waiting = !!r.will_reply; setTyping(waiting); schedule();
        })
        .catch(function (e) {
          bubble.remove(); input.value = text; grow();
          if (sending) { photo = sending; pv.innerHTML = '<span class="th"><img alt="" src="' + sending.url + '"><button class="rm" aria-label="' + esc(t.remove) + '">&times;</button></span>'; pv.classList.add("on"); pv.querySelector(".rm").addEventListener("click", clearPhoto); }
          note(e.status === 429 ? t.busy : t.error);
        })
        .then(function () { sendBtn.disabled = false; });
    }

    if (started) { loaded = true; loadHistory(); }   // so a team reply can light the dot
    document.addEventListener("visibilitychange", function () { if (!document.hidden) schedule(); });
  }
})();

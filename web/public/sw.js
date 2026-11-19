// Inbora panel service worker: shows alerts pushed by the server.
self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { body: event.data && event.data.text() }; }
  event.waitUntil(self.registration.showNotification(data.title || "Inbora", {
    body: data.body || "",
    icon: "/icon.png",
    badge: "/icon.png",
    tag: data.url || "inbora",
    renotify: true,
    data: { url: data.url || "/inbox" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || "/inbox", self.location.origin);
  // Always open on this panel's own address.
  const target = self.location.origin + url.pathname + url.search;
  event.waitUntil((async () => {
    const all = await clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of all) {
      if (c.url.startsWith(self.location.origin) && "focus" in c) {
        try { await c.navigate(target); } catch (e) {}
        return c.focus();
      }
    }
    return clients.openWindow(target);
  })());
});

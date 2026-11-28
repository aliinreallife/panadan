// Never restore a previous tenant's page from the browser back-forward cache.
window.addEventListener("pageshow", event => {
  if (event.persisted) window.location.reload();
});

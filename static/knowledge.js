// Prevent a cached page from showing a previous tenant before revalidation.
// This is presentation hygiene, not revocation of already disclosed data.
window.addEventListener("pagehide", event => {
  if (event.persisted) document.querySelector(".k-shell")?.replaceChildren();
});
window.addEventListener("pageshow", event => {
  if (event.persisted) window.location.reload();
});

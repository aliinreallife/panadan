// Prevent a cached page from showing a previous tenant before revalidation.
// This is presentation hygiene, not revocation of already disclosed data.
window.addEventListener("pagehide", event => {
  if (event.persisted) document.querySelector(".k-shell")?.replaceChildren();
});
window.addEventListener("pageshow", event => {
  if (event.persisted) window.location.reload();
});

const mobileMenu = document.querySelector(".mobile-menu");
const navigation = document.getElementById("workspace-navigation");
if (mobileMenu && navigation) {
  mobileMenu.hidden = false;
  mobileMenu.addEventListener("click", () => {
    const expanded = mobileMenu.getAttribute("aria-expanded") === "true";
    mobileMenu.setAttribute("aria-expanded", String(!expanded));
  });
  const closeMenu = event => {
    if (event.key === "Escape" && mobileMenu.getClientRects().length &&
        mobileMenu.getAttribute("aria-expanded") === "true") {
      mobileMenu.setAttribute("aria-expanded", "false");
      mobileMenu.focus();
    }
  };
  mobileMenu.addEventListener("keydown", closeMenu);
  navigation.addEventListener("keydown", closeMenu);
}

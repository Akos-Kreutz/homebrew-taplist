# Recommendations

Suggested changes found while reading the code. Nothing here is implemented. Part of [Architecture Overview](architecture-overview.md).

---

## Bugs and gaps

* **A bind-mounted empty folder breaks the admin page.** The image ships `mount/background.png`, `favicon.png` and `img/`. Mounting an empty host folder over `/app/mount` hides them: `/admin` then fails on `IMG_DIR.iterdir()` and adding a beverage fails on the missing `img/` folder. Create the folders at start (`IMG_DIR.mkdir(parents=True, exist_ok=True)`), and fall back to a built-in background and favicon.
* **A picture is required for every beverage,** also for a bottle or spirit that has none. Make it optional (the page already handles a missing `image`).
* **Adding a column needs a manual migration.** `metadata.create_all()` creates missing tables but never alters an existing one (see the [guide](guides/new-attribute.md)). A small migration step, or Alembic, would remove that trap.
* **No edit.** To change a beverage it has to be deleted and added again, with a new picture upload. An edit form would also keep the ID stable.
* **Tap replacement is silent.** Adding a tap with an existing number deletes the old one without a warning on the form.

## Versions and docs

* `.docker` says version `2.2`, the Changelog ends at `2.1`.
* The Changelog and README mention a GitHub Actions workflow (Trivy) and Dependabot, but the checkout has no `.github` folder.

## Security and robustness

* **`style-src 'unsafe-inline'`.** It is needed for the inline card colors. Setting the color through a CSS custom property set by a nonce-protected script, or classes per SRM step, would allow removing it.
* **CDN for the admin styles.** The admin page needs jsDelivr to be reachable. Vendoring Bootstrap into `static/` would make the app work offline and remove the CDN from the CSP.
* **Session protection `strong`** logs the admin out when the client address changes (a phone moving between Wi-Fi and mobile data, or IPv4/IPv6). The Drive Catalogue chose `basic` for this reason.
* **Single shared admin, in-memory limiter.** Same limits as the other Flask projects here; fine for one worker.
* **No backup.** The state is the mount folder; a copy of `taplist.db` and `img/` is the backup. A note in the README or a small script would help.
* **No tests.** Candidates: `parse_number` limits, `srm_to_hex`, `sanitize_image` with a mismatched extension, the tap override, the legacy import.
* **Everything in one file.** About 730 lines; splitting out the database part and the admin routes would help once more features come.

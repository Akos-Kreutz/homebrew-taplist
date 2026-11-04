# Beverages & Admin

The data model, how a card is made, and what the admin page does. Part of [Architecture Overview](architecture-overview.md).

---

## The `beverages` table

| Column | Type | Meaning |
|---|---|---|
| `id` | string(36), primary key | A generated UUID. Two beverages may have the same name |
| `category` | string(20), indexed | `taps`, `bottles` or `spirits` (anything else is ignored by the page) |
| `name` | text, required | At most 200 characters |
| `style` | text | At most 200 characters |
| `info` | text | Extra text on the card, at most 1000 characters |
| `untappd` | text | A link; must be `http(s)` on `untappd.com` or a subdomain |
| `image` | text | The path of the picture, normally `/mount/img/<ID>.<ext>` |
| `number` | integer | Tap number or bottle cap number; also the sort key. 0 to 99999. **Required for taps** |
| `abv` | float | Alcohol by volume, 0 to 100 |
| `color` | float | SRM, 0 to 50 |
| `color_hex` | string(7) | Only set by the `drinks.json` import, for hand-set `#rrggbb` colors |
| `ibu` | integer | 0 to 1000, ignored for spirits |
| `kcal` | integer | Calories per 100 ml, 0 to 10000 |

The same ranges are enforced by `parse_number()` (NaN and infinity are refused too) and `parse_text()` on the admin form.

## How the page is built

`index()` loads all rows, groups them by category, and for each item `normalize_drink()` adds:

* `display_color_hex`: `srm_to_hex()` takes the SRM `color`, finds the closest key of `srm_colors.json` and uses its hex value. With no SRM, a stored `color_hex` is used, and otherwise the grey `#333333`.
* `display_ibu` for the card text (`display_srm` is computed as well, but no template shows it).
* The Untappd link is checked **again** at render time (`is_safe_untappd_url`) because the database may have been edited by hand; an unsafe link is dropped.

Then each category is sorted by `number` (missing numbers last, as 9999) and by name. The template draws a card per item with a background of the beer color plus alpha `95`, the number, name, style, info, IBU / ABV / kcal, an Untappd link and the picture (clickable to enlarge). Spirits do not show the number.

## The admin page

All forms are plain `POST` with a CSRF token.

* **Add a beverage** (`add_item`). The category must be one of the three. Text and number fields are validated; a bad value shows a message and returns. A **picture is required**, with the extension `.png .jpg .jpeg .gif .webp`; its content must really be that format. The picture is re-encoded by `sanitize_image()` and saved as `mount/img/<new ID>.<ext>`. For a **tap, a tap with the same number is replaced**: its row is deleted in the same transaction, and its picture is removed unless another beverage still uses it. If the insert fails the new file is removed again.
* **Delete a beverage** (`delete_item`). By ID, so equal names are no problem. The picture is deleted only when it is under `/mount/img/` and no other row uses it.
* **Replace the background** and **the favicon**: PNG only, re-encoded, written over `mount/background.png` and `mount/favicon.png`.

A `threading.Lock` (`WRITE_LOCK`) serializes adding and deleting across the gunicorn threads.

### Picture handling (`sanitize_image`)

Pillow opens the upload, the detected format must equal the format of the extension, the pixel count must be at most 40 million (decompression bomb guard), `verify()` is called and the image is **re-opened and saved again** in the same format (animation kept, JPEG quality kept). Metadata and anything appended to the file are gone. The upload limit of the request is 10 MB.

## Migration from `drinks.json`

Releases before 2.1 stored the beverages in `mount/drinks.json`. At start, if that file exists and the table is **empty**, `import_legacy_drinks()` inserts its items (a new UUID for each), keeps the old `srm` field as `color` and hand-set hex colors as `color_hex`, skips items without a name, and renames the file to `drinks.json.migrated`. If the table is not empty the file is ignored with a warning.

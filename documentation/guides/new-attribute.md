# Guide: a new beverage attribute

How to add one more field to a beverage. The example adds `origin` (the country, text, optional). Part of [Guides](../guides/README.md).

> Related: [Beverages & Admin](../beverages-and-admin.md) · [Recommendations](../recommendations.md)

---

## Steps

### 1. The column

In `app.py`, add it to the `beverages` table:

```python
Column("origin", Text),
```

`create_all()` does **not** change an existing table. A new install gets the column; an existing database needs it added by hand once:

```
# SQLite (the file in the mount folder)
docker exec taplist python3 -c "import sqlite3; c=sqlite3.connect('/app/mount/taplist.db'); c.execute('ALTER TABLE beverages ADD COLUMN origin TEXT'); c.commit()"
# PostgreSQL
ALTER TABLE beverages ADD COLUMN origin TEXT;
```

(The container filesystem is read-only but the mount folder is writable.)

### 2. Read and validate it

In `add_item()`:

```python
origin = parse_text("origin")          # text: optional, max 200 characters
```

and add `"origin": origin` to the `item` dictionary. For a number use `NUMERIC_FIELDS` instead: an entry `"field": (int or float, min, max)` is parsed by the existing loop and appears in `numbers`.

### 3. The form

In `templates/admin.html`, inside the *Add Beverage* form, copy the *Style* input and rename it to `origin`.

### 4. The card

In `templates/index.html`, show it inside `.beer-info` for each of the sections (taps, bottles, spirits):

```html
{% if b.origin %}<div class="beer-extra">{{ b.origin }}</div>{% endif %}
```

Jinja escapes the value. Do not use `|safe`.

### 5. The old import

`import_legacy_drinks()` only knows the old `drinks.json` fields; nothing to do unless the new field must also be read from there.

### 6. Try it

Run the app (`SECRET_KEY` and `ADMIN_PASS` in the environment), add a beverage with the field, check the card, check that an empty value hides the line. Update the attribute list in the README and the [Beverages & Admin](../beverages-and-admin.md) page.

---

## Checklist

* [ ] Column in `beverages`, and `ALTER TABLE` run on the existing database
* [ ] Validated in `add_item()` (length or range) and stored in `item`
* [ ] Input in `admin.html`, display in `index.html` for the sections that need it
* [ ] README and wiki attribute lists updated

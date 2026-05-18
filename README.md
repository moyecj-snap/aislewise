# Aislewise MVP

Aislewise is a photo-based wine recommendation MVP. The app asks for budget,
food, and occasion, accepts a shelf photo, and returns one top pick plus one
backup from wines detected in the image.

## Local Frontend

The current frontend is static HTML/CSS/JS.

```bash
python3 -m http.server 5173 --bind 0.0.0.0
```

Then open `http://127.0.0.1:5173`.

To point the static frontend at a deployed Render API, copy `config.example.js`
to `config.js` and update `window.WINE_AISLE_API_URL`.

Current Render API:

```text
https://aislewise.onrender.com
```

## Deploy

1. Deploy this repo to Netlify with publish directory `.`.
2. Deploy the `api/` folder to Render.
3. Confirm the Render URL in `netlify.toml` is `https://aislewise.onrender.com`.
4. Run `supabase/schema.sql` in Supabase SQL editor.
5. Import `supabase/seed_wines.csv` into the `wines` table.

## Environment Variables

Render API:

- `ALLOWED_ORIGINS`: comma-separated frontend origins, for example `https://your-site.netlify.app`
- `SUPABASE_URL`: Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY`: server-side key for Supabase REST calls
- `OPENAI_API_KEY`: optional; enables real image extraction
- `OPENAI_VISION_MODEL`: defaults to `gpt-5-mini`

The API works without secrets by using the bundled seed CSV and a deterministic
demo extraction path.

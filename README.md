# Fan Hub Plus — Frontend

## Running it

You can now just **open `index.html` directly in your browser** (double-click it,
or File → Open). No server required — every stylesheet, script, and shared
navbar/footer uses paths relative to the file, so it works straight from disk.

If you'd rather run it through a local server (optional, e.g. for a closer
match to production, or if your browser is picky about local scripts), any of
these work fine from this folder too:

```
python3 -m http.server 8080
```
or the VS Code "Live Server" extension. Either way, opening `pages/...` files
directly (not just `index.html`) also works, since every page is self-contained.

## Backend

`js/api-config.js` points at `http://localhost:8000/api` by default. Until
that's running, every page falls back to sample/placeholder data automatically
(see `apiGet`/`apiSend` in that file) — the UI won't break, it'll just show
placeholder content.

## What changed in this cleanup

- All CSS/JS/page links were switched from root-absolute paths (`/css/...`,
  `/pages/...`) to paths relative to each file, so the site no longer depends
  on being served from a domain root.
- The navbar and footer are now inlined directly into every page instead of
  being loaded at runtime via `fetch()` — `fetch()` of local files is blocked
  by the browser's CORS rules when a page is opened directly (`file://`),
  which was the main reason the navbar/footer (and the styling that depends
  on them) weren't showing up.
- `js/main.js` now computes a runtime site-root (`window.FH_ROOT`) from its
  own `<script>` tag, so JS-generated links (e.g. "view content" links from
  `content-explorer.js`, `dashboard.js`, `bookmarks.js`, the post-login
  redirect in `auth.js`) resolve correctly no matter how deep the current
  page is nested, or where the site ends up hosted.
- Removed a stray, non-functional directory left over from a broken build
  script (a literal folder named `{pages/categories,pages/admin,...}` —
  the brace-expansion in whatever `mkdir -p {a,b,c}` command generated this
  zip didn't run in a shell that supports it). Added real `assets/images`,
  `assets/icons`, and `assets/media` folders in its place.
- Note: the project currently has no `<img>` tags or background-images
  anywhere — thumbnails/avatars are all styled placeholder `<div>`s. That's
  not a broken link, there's just no image wiring yet. Say the word if you
  want real `<img>` tags added pointing at `assets/images`.

## Backend connection

`js/api-config.js` points at `http://localhost:8000/api/v1` (change `API_BASE` for a deployed URL).
All JS files use the real API field names (`id`, `category_slug`, `items`, `access_token`, ...).

API gaps handled in the frontend:
- No `/media` endpoint: the multimedia center reuses `/content` filtered by type.
- No `/admin/users` list endpoint: the manage-users table shows a notice and role totals from `/admin/stats`.
- No endpoint to edit only a bookmark's note: `notes.js` deletes and recreates the bookmark.
- Access tokens refresh automatically: on a 401 the frontend calls `/auth/refresh` once and retries; if that fails the session is cleared.
- Admin pages check `/auth/me` and show an "Admins only" notice for non-admins.
- The home fandom row and multimedia type chips are built from `/categories` and the content types actually returned by `/content` (static markup is only the offline fallback).

## Login / sign-in flow
- Pages: `pages/login.html`, `pages/register.html`, `pages/forgot-password.html`.
- Logged out: the top-bar profile icon and the bottom 👤 tab go to the login page; logged in they go to the profile page.
- `dashboard`, `profile`, `bookmarks` and `fan-submissions` redirect to login when there is no token, then return you to the page you wanted (`?next=`, same-site .html paths only).
- The home page "New here?" card (Create account / Log in) is shown to guests only.

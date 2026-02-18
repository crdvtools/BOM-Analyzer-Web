# Railway Deployment Guide
## BOM Analyzer Web — crdvtools
### Why Railway? Streamlit Community Cloud blocks supplier API calls (Mouser, Nexar, Groq). Railway has unrestricted internet access on its free tier.

---

## ⏱ Total Time: ~15 Minutes

---

## STEP 1 — Add These Files to Your GitHub Repo (2 min)

Upload these 3 new files to your `crdvtools/BOM-Analyzer-Web` repository
(same way you uploaded the original files — drag and drop):

| File | Purpose |
|---|---|
| `Procfile` | Tells Railway how to start the app |
| `railway.json` | Railway project configuration |
| `nixpacks.toml` | Specifies Python 3.11 environment |

Keep all your existing files (`app.py`, `requirements.txt`, etc.) — just ADD these 3.

Commit message: `add: Railway deployment configuration`

---

## STEP 2 — Create a Railway Account (2 min)

1. Go to **https://railway.app**
2. Click **"Start a New Project"**
3. Click **"Login with GitHub"** — sign in with the same GitHub account as crdvtools
4. Authorize Railway to access your GitHub

> **Free tier includes:** 500 hours/month (~21 days of continuous runtime).
> For a team tool used during business hours only, this is more than sufficient.
> No credit card required to start.

---

## STEP 3 — Deploy from GitHub (5 min)

1. In Railway dashboard, click **"New Project"**
2. Select **"Deploy from GitHub repo"**
3. Find and select **`crdvtools/BOM-Analyzer-Web`**
4. Railway will auto-detect the `Procfile` and start building
5. Watch the build logs — it takes 2–3 minutes to install dependencies

You'll see log output like:
```
=== Nixpacks Build ===
Installing Python 3.11...
Installing requirements...
Successfully installed streamlit pandas numpy requests matplotlib
=== Build Complete ===
Starting: streamlit run app.py ...
```

---

## STEP 4 — Get Your Public URL (1 min)

1. Once deployed, click on your service in Railway
2. Go to **"Settings"** tab → **"Networking"** section
3. Click **"Generate Domain"**
4. Railway gives you a free URL like:
   `https://bom-analyzer-web-production.up.railway.app`

**Share this URL with your team.** It works in any browser, no installation needed.

---

## STEP 5 — Verify APIs Work (2 min)

1. Open your Railway URL in a browser
2. Enter your Mouser API key in the sidebar: `XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX`
3. Upload your BOM CSV
4. Click **"Run BOM Analysis"**
5. You should now see live pricing data from Mouser ✅

---

## STEP 6 — Keep It Running (Optional)

Railway's free tier sleeps after inactivity. To keep it always-on:

**Option A (Free):** Set up a free uptime monitor at https://uptimerobot.com
- Create a free account
- Add "HTTP(S)" monitor pointing to your Railway URL
- Set check interval to 5 minutes
- This pings the app regularly so it never sleeps

**Option B (Paid $5/mo):** Upgrade Railway to Hobby plan for guaranteed always-on

---

## TROUBLESHOOTING

| Problem | Solution |
|---|---|
| Build fails | Check Railway logs — usually a missing dependency. Add it to `requirements.txt` |
| App crashes on start | Check logs for Python errors. Most common: port binding issue (already handled in `Procfile`) |
| APIs still not working | Railway app is working but key is wrong — double-check key has no spaces |
| "Application failed to respond" | App is sleeping — visit the URL once to wake it, then try again |
| Slow first load | Normal — Railway spins up the container on first visit (~10 sec) |

---

## UPDATING THE APP

When you push changes to GitHub, Railway auto-redeploys:
1. Edit `app.py` in GitHub (or push via git)
2. Railway detects the change automatically
3. Redeploys in ~2 minutes with zero downtime

---

## YOUR DEPLOYMENT SUMMARY

| Item | Value |
|---|---|
| Platform | Railway (railway.app) |
| Repository | github.com/crdvtools/BOM-Analyzer-Web |
| Runtime | Python 3.11 + Streamlit |
| Monthly cost | Free (500 hrs/month) |
| API access | Unrestricted (Mouser, Nexar, Groq all work) |
| Team access | Public URL, any browser |
| Auto-deploy | Yes, on every GitHub push |

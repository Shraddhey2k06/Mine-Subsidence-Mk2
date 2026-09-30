# MineWatch — GitHub Pages Deployment

This repository contains the **GitHub Pages static demonstration** of MineWatch for SIH26025.

## Deploy

1. Create a GitHub repository, for example `Mine-Subsidence-Mk2`.
2. Upload **all files in this folder** to the repository root.
3. Go to **Settings → Pages**.
4. Under **Build and deployment**, select **Deploy from a branch**.
5. Select branch `main` and folder `/ (root)`.
6. Save and wait for GitHub Pages to publish.
7. Open `https://YOUR-USERNAME.github.io/Mine-Subsidence-Mk2/`.

## Important

This Pages version runs the sensor simulator, risk scoring, alerts, charting and GIS visualization **in the browser**. It does not run the Python/Flask backend, SQLite database or server-side ML models because GitHub Pages is a static hosting service.

The original Flask implementation can be kept in a separate backend repository/server if a real API is required. This Pages build is intended as a self-contained SIH demonstration and uses simulated data.

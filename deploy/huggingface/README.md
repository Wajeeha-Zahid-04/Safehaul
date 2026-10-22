---
title: SafeHaul API
emoji: 🚚
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# SafeHaul API

Django REST backend for [SafeHaul](https://github.com/Wajeeha-Zahid-04/Safehaul), a truck route
safety planner. Endpoints: `GET /api/geocode`, `POST /api/plan`, `POST /api/heatmap`.

The image is built from the GitHub repo's `backend/` directory (see `Dockerfile`).
Configure it under **Settings → Variables and secrets**.

# ---------- build ----------
FROM node:18-alpine AS build
WORKDIR /app

# 1) Install deps (ignore stale lockfiles)
#    Copy ONLY package.json so Docker layer caching still works.
COPY services/web/package.json ./package.json
RUN npm install --no-audit --no-fund

# 2) Copy sources
COPY services/web/index.html ./index.html
COPY services/web/vite.config.js ./vite.config.js
COPY services/web/src ./src

# 3) Build
RUN npm run build
RUN ls -lah dist && test -f dist/index.html

# ---------- serve ----------
FROM nginx:1.29-alpine
COPY services/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/ /usr/share/nginx/html/
EXPOSE 80

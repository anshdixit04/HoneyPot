FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY index.html vite.config.js ./
COPY src ./src
# Node auto-sizes the V8 heap conservatively on low-RAM hosts (this image
# builds fine locally but was OOM-aborting on a 1GB VPS); raise the cap
# explicitly rather than relying on the heuristic guessing right.
RUN NODE_OPTIONS=--max-old-space-size=1536 npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

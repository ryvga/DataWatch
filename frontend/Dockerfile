# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app
ARG VITE_BASE_DOMAIN=panopta.app
ARG VITE_ADMIN_SUBDOMAIN=admin
ARG VITE_PAYPAL_CLIENT_ID=sb
ENV VITE_BASE_DOMAIN=$VITE_BASE_DOMAIN \
    VITE_ADMIN_SUBDOMAIN=$VITE_ADMIN_SUBDOMAIN \
    VITE_PAYPAL_CLIENT_ID=$VITE_PAYPAL_CLIENT_ID
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# ── Stage 2: serve with nginx ─────────────────────────────────────────────────
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

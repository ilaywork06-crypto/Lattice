# ---------- Build stage ----------
FROM node:22-alpine AS build

WORKDIR /app

# Build-time API URLs (baked into the static bundle by Vite)
ARG VITE_CORE_API_URL=http://localhost:8000
ARG VITE_NOTIFICATION_API_URL=http://localhost:8001
ENV VITE_CORE_API_URL=$VITE_CORE_API_URL
ENV VITE_NOTIFICATION_API_URL=$VITE_NOTIFICATION_API_URL

# Install dependencies from lockfile for reproducible builds
COPY package.json package-lock.json* ./
RUN npm ci

# Build the production bundle
COPY . .
RUN npm run build

# ---------- Runtime stage ----------
FROM nginx:alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

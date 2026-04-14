FROM node:22-alpine

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Source code mounted as volume — no COPY needed
CMD ["sh", "-c", "npm ci && npm run dev -- --host 0.0.0.0"]

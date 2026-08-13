FROM node:24-alpine AS build
WORKDIR /app
COPY apps/web/package.json ./package.json
RUN npm install
COPY apps/web ./
RUN npm run build

FROM node:24-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup -S traderx && adduser -S traderx -G traderx
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
# The macOS/Windows MT5 Expert Advisor is a deliberately auditable source download, served by
# the authenticated setup UI; it is not bundled into the server-side application image code.
COPY apps/mt5_bridge/mql5/TraderXReadOnlyBridge.mq5 ./public/mt5-bridge/TraderXReadOnlyBridge.mq5
USER traderx
EXPOSE 3000
CMD ["node", "server.js"]

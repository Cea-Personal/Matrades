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
USER traderx
EXPOSE 3000
CMD ["node", "server.js"]

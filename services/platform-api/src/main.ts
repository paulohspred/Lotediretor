import "reflect-metadata";
import { NestFactory } from "@nestjs/core";
import { FastifyAdapter, NestFastifyApplication } from "@nestjs/platform-fastify";
import rateLimit from "@fastify/rate-limit";
import { AppModule } from "./app.module.js";

async function bootstrap() {
  const app = await NestFactory.create<NestFastifyApplication>(
    AppModule,
    new FastifyAdapter({ trustProxy: true }),
  );
  app.enableShutdownHooks();
  // Coarse per-IP protection; per-user quotas (e.g. AI) are enforced in services.
  await app.register(rateLimit, {
    max: Number(process.env.RATE_LIMIT_PER_MINUTE ?? 300),
    timeWindow: "1 minute",
    errorResponseBuilder: () => ({
      statusCode: 429,
      code: "RATE_LIMITED",
      message: "Muitas requisições. Tente novamente em instantes.",
    }),
  });

  const port = Number(process.env.PORT ?? 3000);
  const host = process.env.HOST ?? "127.0.0.1";
  await app.listen(port, host);
}

void bootstrap();

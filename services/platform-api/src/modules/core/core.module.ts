import { Controller, Get, Module } from "@nestjs/common";
import { Query, Resolver } from "@nestjs/graphql";

@Controller()
class HealthController {
  @Get("/healthz")
  health() {
    return {
      ok: true,
      service: "lotediretor-platform-api",
      architecture: "modular-monolith",
    };
  }
}

@Resolver()
class PlatformResolver {
  @Query(() => String)
  platformStatus(): string {
    return "ok";
  }
}

@Module({
  controllers: [HealthController],
  providers: [PlatformResolver],
})
export class CoreModule {}

import {
  Body,
  Controller,
  Get,
  HttpCode,
  Module,
  Param,
  Post,
} from "@nestjs/common";
import {
  ParcelEngineService,
  ParcelResolveInput,
} from "./parcel-engine.service.js";

@Controller()
class ParcelController {
  constructor(private readonly engine: ParcelEngineService) {}

  @Post("/parcel/resolve")
  @HttpCode(200)
  resolve(@Body() body: ParcelResolveInput) {
    return this.engine.resolve(body);
  }

  @Get("/analysis/:analysisRunId/evidence")
  evidence(@Param("analysisRunId") analysisRunId: string) {
    return this.engine.evidence(analysisRunId);
  }
}

@Module({
  controllers: [ParcelController],
  providers: [ParcelEngineService],
  exports: [ParcelEngineService],
})
export class GeoModule {}

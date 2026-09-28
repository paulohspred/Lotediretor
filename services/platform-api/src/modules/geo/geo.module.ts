import {
  Body,
  Controller,
  Get,
  HttpCode,
  Module,
  Param,
  Post,
  Query,
} from "@nestjs/common";
import {
  ParcelEngineService,
  ParcelResolveInput,
  ParcelSearchInput,
} from "./parcel-engine.service.js";

@Controller()
class ParcelController {
  constructor(private readonly engine: ParcelEngineService) {}

  @Post("/parcel/resolve")
  @HttpCode(200)
  resolve(@Body() body: ParcelResolveInput) {
    return this.engine.resolve(body);
  }

  @Get("/parcel/search")
  search(
    @Query("municipality_ibge") municipality_ibge: string,
    @Query("q") q: string,
  ) {
    const input: ParcelSearchInput = { municipality_ibge, q };
    return this.engine.search(input);
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

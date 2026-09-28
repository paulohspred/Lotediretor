import { Body, Controller, Module, Post } from "@nestjs/common";
import {
  ParcelEngineService,
  ParcelResolveInput,
} from "./parcel-engine.service.js";

@Controller()
class ParcelController {
  constructor(private readonly engine: ParcelEngineService) {}

  @Post("/parcel/resolve")
  resolve(@Body() body: ParcelResolveInput) {
    return this.engine.resolve(body);
  }
}

@Module({
  controllers: [ParcelController],
  providers: [ParcelEngineService],
  exports: [ParcelEngineService],
})
export class GeoModule {}

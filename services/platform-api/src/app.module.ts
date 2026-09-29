import { Module } from "@nestjs/common";
import { GraphQLModule } from "@nestjs/graphql";
import {
  MercuriusDriver,
  MercuriusDriverConfig,
} from "@nestjs/mercurius";
import { CoreModule } from "./modules/core/core.module.js";
import { DatabaseModule } from "./modules/database/database.module.js";
import { GeoModule } from "./modules/geo/geo.module.js";
import { TerritoryModule } from "./modules/territory/territory.module.js";
import { PointContextModule } from "./modules/context/point-context.module.js";

@Module({
  imports: [
    GraphQLModule.forRoot<MercuriusDriverConfig>({
      driver: MercuriusDriver,
      autoSchemaFile: true,
      path: "/graphql",
      graphiql: process.env.NODE_ENV !== "production",
    }),
    DatabaseModule,
    CoreModule,
    TerritoryModule,
    PointContextModule,
    GeoModule,
  ],
})
export class AppModule {}

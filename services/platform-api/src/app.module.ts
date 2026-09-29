import { Module } from "@nestjs/common";
import { GraphQLModule } from "@nestjs/graphql";
import {
  MercuriusDriver,
  MercuriusDriverConfig,
} from "@nestjs/mercurius";
import { CoreModule } from "./modules/core/core.module.js";
import { DatabaseModule } from "./modules/database/database.module.js";
import { AuthModule } from "./modules/auth/account.module.js";
import { GeoModule } from "./modules/geo/geo.module.js";
import { TerritoryModule } from "./modules/territory/territory.module.js";
import { PointContextModule } from "./modules/context/point-context.module.js";
import { LegalModule } from "./modules/legal/legal.module.js";
import { AiModule } from "./modules/ai/cidades.module.js";
import { AdminModule } from "./modules/admin/admin.module.js";
import { PublicModule } from "./modules/public/public.module.js";
import { ReportModule } from "./modules/reports/report.module.js";

@Module({
  imports: [
    GraphQLModule.forRoot<MercuriusDriverConfig>({
      driver: MercuriusDriver,
      autoSchemaFile: true,
      path: "/graphql",
      graphiql: process.env.NODE_ENV !== "production",
    }),
    DatabaseModule,
    AuthModule,
    CoreModule,
    TerritoryModule,
    PointContextModule,
    LegalModule,
    AiModule,
    AdminModule,
    PublicModule,
    GeoModule,
    ReportModule,
  ],
})
export class AppModule {}

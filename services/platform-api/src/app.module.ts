import { Module } from "@nestjs/common";
import { GraphQLModule } from "@nestjs/graphql";
import {
  MercuriusDriver,
  MercuriusDriverConfig,
} from "@nestjs/mercurius";
import { CoreModule } from "./modules/core/core.module";
import { GeoModule } from "./modules/geo/geo.module";

@Module({
  imports: [
    GraphQLModule.forRoot<MercuriusDriverConfig>({
      driver: MercuriusDriver,
      autoSchemaFile: true,
      path: "/graphql",
      graphiql: process.env.NODE_ENV !== "production",
    }),
    CoreModule,
    GeoModule,
  ],
})
export class AppModule {}

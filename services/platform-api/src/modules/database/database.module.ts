import {
  Global,
  Inject,
  Injectable,
  Module,
  OnApplicationShutdown,
  ServiceUnavailableException,
} from "@nestjs/common";
import pg from "pg";

export const PG_POOL = Symbol("PG_POOL");

/**
 * Connection string for the platform database. Accepts a standard URL
 * (postgresql://user:pass@host/db) or unix-socket form
 * (postgresql:///lotediretor?host=/var/run/postgresql).
 */
export function databaseUrl(): string | undefined {
  return process.env.DATABASE_URL ?? process.env.LOTEDIRETOR_DB_DSN;
}

@Injectable()
export class Database implements OnApplicationShutdown {
  constructor(@Inject(PG_POOL) private readonly pool: pg.Pool | null) {}

  get available(): boolean {
    return this.pool !== null;
  }

  /** Parameterized query only; never interpolate user input into SQL. */
  async query<T extends pg.QueryResultRow>(
    sql: string,
    params: unknown[] = [],
  ): Promise<T[]> {
    if (!this.pool) {
      throw new ServiceUnavailableException({
        code: "DATABASE_NOT_CONFIGURED",
        message: "Base territorial indisponível.",
        retryable: true,
      });
    }
    try {
      const result = await this.pool.query<T>(sql, params);
      return result.rows;
    } catch (error) {
      // Log server-side; never leak SQL or driver details to clients.
      console.error("database query failed", error);
      throw new ServiceUnavailableException({
        code: "DATABASE_ERROR",
        message: "Base territorial temporariamente indisponível.",
        retryable: true,
      });
    }
  }

  async onApplicationShutdown(): Promise<void> {
    await this.pool?.end();
  }
}

@Global()
@Module({
  providers: [
    {
      provide: PG_POOL,
      useFactory: () => {
        const connectionString = databaseUrl();
        if (!connectionString) return null;
        return new pg.Pool({
          connectionString,
          max: Number(process.env.DATABASE_POOL_MAX ?? 10),
          idleTimeoutMillis: 30_000,
          connectionTimeoutMillis: 5_000,
          statement_timeout: 10_000,
          application_name: "lotediretor-platform-api",
        });
      },
    },
    Database,
  ],
  exports: [Database],
})
export class DatabaseModule {}

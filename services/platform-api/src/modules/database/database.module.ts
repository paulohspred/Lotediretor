import {
  Global,
  HttpException,
  Inject,
  Injectable,
  Module,
  OnApplicationShutdown,
  ServiceUnavailableException,
} from "@nestjs/common";
import pg from "pg";

export const PG_POOL = Symbol("PG_POOL");

export type TxQuery = <R extends pg.QueryResultRow>(
  sql: string,
  params?: unknown[],
) => Promise<R[]>;

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

  /**
   * Run statements in one transaction with the tenant set for row-level
   * security (ld.org_id). Tenant data must only be touched through here.
   */
  async withOrg<T>(orgId: string, fn: (q: TxQuery) => Promise<T>): Promise<T> {
    return this.transaction(fn, orgId);
  }

  /** Transaction without tenant context (non-RLS tables only). */
  async transaction<T>(fn: (q: TxQuery) => Promise<T>, orgId = ""): Promise<T> {
    if (!this.pool) {
      throw new ServiceUnavailableException({
        code: "DATABASE_NOT_CONFIGURED",
        message: "Base indisponível.",
        retryable: true,
      });
    }
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      await client.query("SELECT set_config('ld.org_id', $1, true)", [orgId]);
      const result = await fn(async <R extends pg.QueryResultRow>(sql: string, params: unknown[] = []) =>
        (await client.query<R>(sql, params)).rows,
      );
      await client.query("COMMIT");
      return result;
    } catch (error) {
      await client.query("ROLLBACK").catch(() => undefined);
      if (error instanceof HttpException) throw error;
      console.error("tenant transaction failed", error);
      throw new ServiceUnavailableException({
        code: "DATABASE_ERROR",
        message: "Operação indisponível no momento.",
        retryable: true,
      });
    } finally {
      client.release();
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

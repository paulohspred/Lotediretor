import { Controller, Get, Injectable, Module, NotFoundException, Param, Res, UseGuards } from "@nestjs/common";
import type { FastifyReply } from "fastify";
import { Database } from "../database/database.module.js";
import { AccountGuard, CurrentAccount, type Account } from "../auth/account.module.js";
import { GeoModule } from "../geo/geo.module.js";
import { ParcelEngineService } from "../geo/parcel-engine.service.js";
import { createTextPdf, dossierLines } from "./simple-pdf.js";

@Injectable()
class ReportService {
  constructor(private readonly db:Database, private readonly engine:ParcelEngineService){}

  async propertyPdf(account:Account,id:string){
    const property=await this.db.withOrg(account.active_org.org_id,async q=>{
      const rows=await q<{saved_property_id:string;ibge_code:string;municipality:string;uf:string;label:string;lat:number;lng:number;parcel_reference:string|null}>(
        `SELECT sp.saved_property_id,sp.ibge_code,m.name municipality,s.uf,sp.label,sp.lat,sp.lng,sp.parcel_reference
         FROM ld_app.saved_property sp JOIN ld_core.municipality m USING(ibge_code) JOIN ld_core.state s USING(uf_code)
         WHERE sp.saved_property_id=$1`,[id]);
      if(!rows[0]) throw new NotFoundException({code:"NOT_FOUND",message:"Imóvel não encontrado."});
      return rows[0];
    });
    const payload=await this.engine.resolve({municipality_ibge:property.ibge_code,lat:Number(property.lat),lng:Number(property.lng)});
    const pdf=createTextPdf("LoteDiretor - Dossiê territorial",dossierLines(property,payload));
    await this.db.withOrg(account.active_org.org_id,async q=>{
      await q(`INSERT INTO ld_app.activity_event(org_id,user_id,kind,summary,payload)
        VALUES($1,$2,'report.pdf.generated',$3,jsonb_build_object('saved_property_id',$4::text,'bytes',$5::int))`,
        [account.active_org.org_id,account.user_id,`Relatório PDF gerado: ${property.label}`,property.saved_property_id,pdf.length]);
    });
    return {pdf,filename:`lotediretor-${property.saved_property_id}.pdf`};
  }
}

@Controller("reports")
@UseGuards(AccountGuard)
class ReportController{
  constructor(private readonly reports:ReportService){}
  @Get("properties/:id.pdf")
  async pdf(@CurrentAccount() account:Account,@Param("id") id:string,@Res({passthrough:true}) reply:FastifyReply){
    const {pdf,filename}=await this.reports.propertyPdf(account,id);
    reply.header("content-type","application/pdf");
    reply.header("content-disposition",`attachment; filename="${filename}"`);
    reply.header("cache-control","private, no-store");
    return pdf;
  }
}

@Module({imports:[GeoModule],controllers:[ReportController],providers:[ReportService]})
export class ReportModule{}

import test from "node:test";
import assert from "node:assert/strict";
import { createTextPdf, dossierLines } from "../dist/modules/reports/simple-pdf.js";

test("simple PDF contains valid header and candidate warning", () => {
  const lines=dossierLines(
    {label:"Lote Centro",municipality:"São Paulo",uf:"SP",parcel_reference:"001"},
    {dossier:{sections:[{title:"Zoneamento",items:[{label:"CA máximo",value:"2,0",unit:"x"}]}]}}
  );
  const pdf=createTextPdf("LoteDiretor - Dossiê territorial",lines);
  assert.equal(pdf.subarray(0,8).toString("binary"),"%PDF-1.4");
  assert.ok(pdf.length>800);
  const binary=pdf.toString("binary");
  assert.match(binary,/CANDIDATE/);
  assert.match(binary,/Zoneamento/);
});

const PAGE_W = 595;
const PAGE_H = 842;
const MARGIN = 48;
const LINE_H = 14;
const MAX_CHARS = 88;

const WIN1252: Record<string, number> = {
  "€":0x80,"‚":0x82,"ƒ":0x83,"„":0x84,"…":0x85,"†":0x86,"‡":0x87,
  "ˆ":0x88,"‰":0x89,"Š":0x8a,"‹":0x8b,"Œ":0x8c,"Ž":0x8e,
  "‘":0x91,"’":0x92,"“":0x93,"”":0x94,"•":0x95,"–":0x96,"—":0x97,
  "˜":0x98,"™":0x99,"š":0x9a,"›":0x9b,"œ":0x9c,"ž":0x9e,"Ÿ":0x9f,
};

function byteFor(ch: string): number {
  const cp=ch.codePointAt(0) ?? 63;
  if (cp<=255) return cp;
  return WIN1252[ch] ?? 63;
}
function pdfEscaped(text:string): string {
  const bytes=Buffer.from(Array.from(text).map(byteFor));
  let out="";
  for(const b of bytes){
    if(b===0x28||b===0x29||b===0x5c) out+="\\"+String.fromCharCode(b);
    else if(b<32||b>126) out+="\\"+b.toString(8).padStart(3,"0");
    else out+=String.fromCharCode(b);
  }
  return out;
}
function wrap(text:string,max=MAX_CHARS):string[]{
  const clean=text.replace(/\s+/g," ").trim();
  if(!clean) return [""];
  const words=clean.split(" "); const lines:string[]=[]; let line="";
  for(const word of words){
    if(!line){line=word;continue;}
    if((line+" "+word).length<=max) line+=" "+word;
    else {lines.push(line); line=word;}
  }
  if(line) lines.push(line);
  return lines;
}
export type PdfLine={text:string;bold?:boolean;gapBefore?:number};

export function createTextPdf(title:string, lines:PdfLine[]):Buffer{
  const expanded:PdfLine[]=[{text:title,bold:true,gapBefore:0},...lines];
  const pages:PdfLine[][]=[]; let page:PdfLine[]=[]; let used=0;
  for(const item of expanded){
    const parts=wrap(item.text,item.bold?76:MAX_CHARS);
    const need=(item.gapBefore??0)+parts.length*LINE_H;
    if(page.length && used+need>PAGE_H-MARGIN*2){pages.push(page);page=[];used=0;}
    if(item.gapBefore) used+=item.gapBefore;
    for(const part of parts){page.push({...item,text:part,gapBefore:0});used+=LINE_H;}
  }
  if(page.length||!pages.length) pages.push(page);

  const objects:Buffer[]=[];
  const add=(s:string|Buffer)=>{objects.push(Buffer.isBuffer(s)?s:Buffer.from(s,"binary"));return objects.length;};
  const font=add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>");
  const bold=add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>");
  const contentIds:number[]=[];
  for(const p of pages){
    let y=PAGE_H-MARGIN; let stream="BT\n";
    for(const item of p){
      y-=item.gapBefore??0;
      const size=item.bold?13:9.5;
      stream+=`/${item.bold?"F2":"F1"} ${size} Tf 1 0 0 1 ${MARGIN} ${y.toFixed(1)} Tm (${pdfEscaped(item.text)}) Tj\n`;
      y-=LINE_H;
    }
    stream+="ET\n";
    const body=Buffer.from(stream,"binary");
    contentIds.push(add(Buffer.concat([Buffer.from(`<< /Length ${body.length} >>\nstream\n`,"binary"),body,Buffer.from("endstream","binary")])));
  }
  const pagesObjIndex=objects.length+1;
  add(""); // placeholder pages
  const pageIds:number[]=[];
  for(const contentId of contentIds){
    pageIds.push(add(`<< /Type /Page /Parent ${pagesObjIndex} 0 R /MediaBox [0 0 ${PAGE_W} ${PAGE_H}] /Resources << /Font << /F1 ${font} 0 R /F2 ${bold} 0 R >> >> /Contents ${contentId} 0 R >>`));
  }
  objects[pagesObjIndex-1]=Buffer.from(`<< /Type /Pages /Count ${pageIds.length} /Kids [${pageIds.map(i=>`${i} 0 R`).join(" ")}] >>`,"binary");
  const catalog=add(`<< /Type /Catalog /Pages ${pagesObjIndex} 0 R >>`);

  const chunks:Buffer[]=[Buffer.from("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n","binary")];
  const offsets=[0]; let pos=chunks[0].length;
  objects.forEach((obj,i)=>{
    offsets.push(pos);
    const chunk=Buffer.concat([Buffer.from(`${i+1} 0 obj\n`,"binary"),obj,Buffer.from("\nendobj\n","binary")]);
    chunks.push(chunk); pos+=chunk.length;
  });
  const xref=pos;
  let trailer=`xref\n0 ${objects.length+1}\n0000000000 65535 f \n`;
  for(let i=1;i<offsets.length;i++) trailer+=String(offsets[i]).padStart(10,"0")+" 00000 n \n";
  trailer+=`trailer\n<< /Size ${objects.length+1} /Root ${catalog} 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  chunks.push(Buffer.from(trailer,"binary"));
  return Buffer.concat(chunks);
}

function printable(value:unknown):string{
  if(value===null||value===undefined||value==="") return "não disponível";
  if(typeof value==="string"||typeof value==="number"||typeof value==="boolean") return String(value);
  return JSON.stringify(value);
}

export function dossierLines(property:{label:string;municipality:string;uf:string;parcel_reference:string|null}, payload:any):PdfLine[]{
  const lines:PdfLine[]=[
    {text:`Imóvel: ${property.label}`,bold:true,gapBefore:8},
    {text:`Município: ${property.municipality} - ${property.uf}`},
    {text:`Referência cadastral: ${property.parcel_reference ?? "não disponível"}`},
    {text:"Aviso: regras com status CANDIDATE são extrações automáticas ainda não confirmadas e não devem ser tratadas como decisão urbanística definitiva.",gapBefore:10},
  ];
  const sections=payload?.dossier?.sections ?? payload?.report?.sections ?? [];
  for(const section of sections){
    lines.push({text:String(section.title ?? section.id ?? "Seção"),bold:true,gapBefore:10});
    const items=section.items ?? section.actual_values ?? [];
    for(const item of items){
      const unit=item.unit ? ` ${item.unit}`:"";
      let text=`${item.label ?? "Informação"}: ${printable(item.value)}${unit}`;
      const source=item.source?.authority ?? item.authority;
      const date=item.source?.date ?? item.source_date ?? item.loaded_at;
      if(source) text+=`. Fonte: ${source}`;
      if(date) text+=`. Data: ${String(date).slice(0,10)}`;
      lines.push({text});
    }
  }
  const sourceRefs=payload?.sources ?? payload?.analysis?.sources;
  if(sourceRefs){
    lines.push({text:"Fontes e proveniência",bold:true,gapBefore:10});
    lines.push({text:printable(sourceRefs)});
  }
  lines.push({text:"Este relatório é apoio técnico. Confirme exigências, vigência e aprovação junto ao órgão competente.",gapBefore:12});
  return lines;
}

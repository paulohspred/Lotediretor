export const COMPANY = {
  name: process.env.NEXT_PUBLIC_COMPANY_NAME ?? "[razão social a preencher]",
  cnpj: process.env.NEXT_PUBLIC_COMPANY_CNPJ ?? "[CNPJ a preencher]",
  address: process.env.NEXT_PUBLIC_COMPANY_ADDRESS ?? "[endereço a preencher]",
  dpoEmail: process.env.NEXT_PUBLIC_DPO_EMAIL ?? "[e-mail do encarregado a preencher]",
  reviewed: process.env.NEXT_PUBLIC_LEGAL_REVIEWED === "true",
  updatedAt: process.env.NEXT_PUBLIC_LEGAL_UPDATED_AT ?? "28/09/2026",
};

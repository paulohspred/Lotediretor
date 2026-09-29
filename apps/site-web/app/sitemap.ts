import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/content";

const PATHS = ["/", "/solucoes", "/como-funciona", "/prefeituras", "/planos", "/contato", "/privacidade", "/termos"];

export default function sitemap(): MetadataRoute.Sitemap {
  return PATHS.map((path) => ({ url: `${SITE_URL}${path}`, changeFrequency: "monthly" }));
}

import { cache } from "react";
import { apiGet, type Me } from "@/lib/api";

/** The current user's /me, fetched once per request and shared by the layout and pages. */
export const getMe = cache(() => apiGet<Me>("/me"));

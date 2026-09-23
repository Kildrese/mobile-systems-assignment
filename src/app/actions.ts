"use server";

import { revalidatePath } from "next/cache";
import { getDb } from "@/db";
import { notes } from "@/db/schema";

export async function addNote(formData: FormData) {
  const content = String(formData.get("content") ?? "").trim();
  if (!content) return;

  await getDb().insert(notes).values({ content });
  revalidatePath("/");
}

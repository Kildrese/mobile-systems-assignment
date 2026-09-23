import { desc } from "drizzle-orm";
import { connection } from "next/server";
import { getDb } from "@/db";
import { notes } from "@/db/schema";
import { addNote } from "./actions";
import styles from "./page.module.css";

export default async function Home() {
  // Render at request time so the list always reflects the database.
  await connection();

  const allNotes = await getDb()
    .select()
    .from(notes)
    .orderBy(desc(notes.createdAt), desc(notes.id));

  return (
    <main className={styles.main}>
      <h1>Notes</h1>

      <form action={addNote} className={styles.form}>
        <input
          type="text"
          name="content"
          placeholder="Write a note…"
          aria-label="Note content"
          required
        />
        <button type="submit">Add</button>
      </form>

      {allNotes.length === 0 ? (
        <p className={styles.empty}>No notes yet. Add the first one above.</p>
      ) : (
        <ul className={styles.list}>
          {allNotes.map((note) => (
            <li key={note.id}>
              <p>{note.content}</p>
              <time dateTime={note.createdAt.toISOString()}>
                {note.createdAt.toLocaleString()}
              </time>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

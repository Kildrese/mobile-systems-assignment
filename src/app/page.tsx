import styles from "./page.module.css";

export default function Home() {
  return (
    <main className={styles.main}>
      <h1>Mobile Systems API</h1>
      <p>
        This app serves a JSON API. Browse and try the endpoints in the{" "}
        <a href="/docs">API reference</a>.
      </p>
    </main>
  );
}

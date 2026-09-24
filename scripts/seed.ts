// Creates the test account: username `NYUgrader`, password `Courant2026!`.
// Safe to run repeatedly: an existing account is left alone.
//
// Run with `npm run db:seed`, which sets the `react-server` condition so the
// server-only account service can be imported outside Next.js.
import "dotenv/config";
import { registerUser } from "@/lib/services/account";

const TEST_USER = {
  username: "nyugrader",
  password: "Courant2026!",
  firstName: "NYU",
  lastName: "Grader",
};

async function main() {
  const result = await registerUser(TEST_USER);
  if (result.ok) console.log(`Created user ${TEST_USER.username}.`);
  else if (result.code === "USERNAME_TAKEN") console.log(`User ${TEST_USER.username} already exists.`);
  else throw new Error(`Seeding ${TEST_USER.username} failed: ${result.code}`);
}

main().then(
  () => process.exit(0),
  (err) => {
    console.error(err);
    process.exit(1);
  },
);

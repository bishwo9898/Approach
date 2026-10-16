/**
 * Live feedback for the password field.
 *
 * A mirror of the server's policy, not the policy itself -- `bsa.core.password`
 * decides, and this file exists so a twelve-year-old finds out what is wrong
 * while typing instead of on submit. Two consequences, both deliberate:
 *
 * * The rules *shown* on screen come from the server (`password_rules` on the
 *   setup response), so the list a person reads can never disagree with the one
 *   actually enforced.
 * * Anything the server rejects is displayed verbatim. If these two ever drift,
 *   the server wins and the person sees why.
 *
 * The common-password list is not duplicated here: it is the server's to carry,
 * and a copy in the bundle would be a list of passwords to try.
 */

export const MIN_LENGTH = 10;

/** Every local reason this password is unacceptable. Empty means "looks fine". */
export function passwordProblems(
  password: string,
  options: { email?: string } = {},
): string[] {
  const problems: string[] = [];

  if (password.length < MIN_LENGTH) {
    problems.push(`Use at least ${MIN_LENGTH} characters.`);
  }
  if (!/[A-Za-z]/.test(password)) problems.push("Include at least one letter.");
  if (!/\d/.test(password)) problems.push("Include at least one number.");
  if (password !== password.trim()) {
    problems.push("Remove the space at the start or end.");
  }
  if (password.length > 0 && new Set(password).size < 5) {
    problems.push("Use a greater variety of characters.");
  }

  // The email local part is the one "personal term" the browser already knows.
  // The athlete's name is the server's to check, since only it holds the roster.
  const local = (options.email ?? "").split("@")[0] ?? "";
  const letters = local.toLowerCase().replace(/[^a-z]/g, "");
  if (
    letters.length >= 4 &&
    password
      .toLowerCase()
      .replace(/[^a-z]/g, "")
      .includes(letters)
  ) {
    problems.push("Don't use your name or email in your password.");
  }

  return problems;
}

/** A coarse label for the strength bar. Never a reason to accept or reject. */
export function passwordStrength(password: string): 0 | 1 | 2 | 3 {
  if (passwordProblems(password).length > 0) return 0;
  let score = 1;
  if (password.length >= 14) score += 1;
  if (/[^A-Za-z0-9]/.test(password) && /[A-Z]/.test(password)) score += 1;
  return Math.min(score, 3) as 0 | 1 | 2 | 3;
}

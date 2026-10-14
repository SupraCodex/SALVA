// Password strength shown while typing (indication only; the server enforces 10 to 128 characters).
// 0 = empty, 1 = weak, 2 = fair, 3 = good, 4 = strong.

export type Strength = 0 | 1 | 2 | 3 | 4;

const COMMON =
  /(password|motdepasse|azerty|qwerty|admin|salva|bienvenue|welcome|soleil|0123|1234|2345|3456|4567|5678|6789|abcd)/i;

export function passwordStrength(password: string): Strength {
  if (!password) return 0;
  if (password.length < 10) return 1;
  if (new Set(password.toLowerCase()).size < 5) return 1;

  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((re) => re.test(password)).length;
  let score = 1;
  if (classes >= 2 || password.length >= 14) score += 1;
  if ((classes >= 3 && password.length >= 12) || (classes >= 2 && password.length >= 16)) score += 1;
  if ((classes >= 3 && password.length >= 14) || (classes === 4 && password.length >= 12) || password.length >= 20) score += 1;

  if (COMMON.test(password)) score -= 1;
  return Math.max(1, Math.min(4, score)) as Strength;
}

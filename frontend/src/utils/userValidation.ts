const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const PASSWORD_UPPERCASE_PATTERN = /[A-Z]/
const PASSWORD_DIGIT_PATTERN = /\d/

export function isValidEmail(email: string) {
  return EMAIL_PATTERN.test(email)
}

export function hasMinimumUsernameLength(username: string) {
  return username.trim().length >= 6
}

export function hasRequiredPasswordComplexity(password: string) {
  return PASSWORD_UPPERCASE_PATTERN.test(password) && PASSWORD_DIGIT_PATTERN.test(password)
}

/** Domain localization boundary. Financial decision codes are stable, language-independent. */
export type Locale = "ru" | "en";
export const labels = {
  ru: {
    APPROVE: "Разрешено",
    ASK: "Требуется согласие",
    DENY: "Запрещено",
    electronics: "Электроника",
  },
  en: {
    APPROVE: "Approved",
    ASK: "Confirmation required",
    DENY: "Denied",
    electronics: "Electronics",
  },
} as const;
export function label(locale: Locale, key: keyof typeof labels.ru) {
  return labels[locale][key];
}

export const LANGUAGES = [
  {
    code: "en",
    name: "English",
    nameNative: "English",
    flag: "🇺🇸",
    whisper: "en",
    translation: "eng_Latn",
  },
  {
    code: "vi",
    name: "Tieng Viet",
    nameNative: "Tiếng Việt",
    flag: "🇻🇳",
    whisper: "vi",
    translation: "vie_Latn",
  },
];

export const DEFAULT_TGT = "en";

export function getLanguage(code) {
  return LANGUAGES.find((language) => language.code === code) || null;
}

export function getTargetLanguages() {
  return LANGUAGES;
}

export function getSourceLanguages() {
  return LANGUAGES;
}

export function saveLanguagePreference(_srcCode, tgtCode) {
  localStorage.setItem("asr_tgtLang", tgtCode);
}

export function loadLanguagePreference() {
  const savedTarget = localStorage.getItem("asr_tgtLang");
  return {
    srcCode: savedTarget === "vi" ? "en" : "vi",
    tgtCode: getLanguage(savedTarget) ? savedTarget : DEFAULT_TGT,
  };
}

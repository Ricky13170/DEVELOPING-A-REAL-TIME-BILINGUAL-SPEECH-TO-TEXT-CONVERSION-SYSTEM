/**
 * Language registry for multi-language ASR support.
 * Each entry maps to WhisperX language codes and NLLB translation codes.
 */
export const LANGUAGES = [
  {
    code: "auto",
    name: "Auto Detect",
    nameNative: "Auto",
    flag: "🌐",
    whisper: null,
    nllb: null,
  },
  {
    code: "vi",
    name: "Vietnamese",
    nameNative: "Tiếng Việt",
    flag: "🇻🇳",
    whisper: "vi",
    nllb: "vie_Latn",
  },
  {
    code: "en",
    name: "English",
    nameNative: "English",
    flag: "🇺🇸",
    whisper: "en",
    nllb: "eng_Latn",
  },
  {
    code: "zh",
    name: "Chinese",
    nameNative: "中文",
    flag: "🇨🇳",
    whisper: "zh",
    nllb: "zho_Hans",
  },
  {
    code: "ja",
    name: "Japanese",
    nameNative: "日本語",
    flag: "🇯🇵",
    whisper: "ja",
    nllb: "jpn_Jpan",
  },
  {
    code: "ko",
    name: "Korean",
    nameNative: "한국어",
    flag: "🇰🇷",
    whisper: "ko",
    nllb: "kor_Hang",
  },
  {
    code: "fr",
    name: "French",
    nameNative: "Français",
    flag: "🇫🇷",
    whisper: "fr",
    nllb: "fra_Latn",
  },
  {
    code: "de",
    name: "German",
    nameNative: "Deutsch",
    flag: "🇩🇪",
    whisper: "de",
    nllb: "deu_Latn",
  },
  {
    code: "es",
    name: "Spanish",
    nameNative: "Español",
    flag: "🇪🇸",
    whisper: "es",
    nllb: "spa_Latn",
  },
  {
    code: "th",
    name: "Thai",
    nameNative: "ไทย",
    flag: "🇹🇭",
    whisper: "th",
    nllb: "tha_Thai",
  },
  {
    code: "id",
    name: "Indonesian",
    nameNative: "Bahasa",
    flag: "🇮🇩",
    whisper: "id",
    nllb: "ind_Latn",
  },
  {
    code: "pt",
    name: "Portuguese",
    nameNative: "Português",
    flag: "🇧🇷",
    whisper: "pt",
    nllb: "por_Latn",
  },
  {
    code: "ru",
    name: "Russian",
    nameNative: "Русский",
    flag: "🇷🇺",
    whisper: "ru",
    nllb: "rus_Cyrl",
  },
  {
    code: "ar",
    name: "Arabic",
    nameNative: "العربية",
    flag: "🇸🇦",
    whisper: "ar",
    nllb: "arb_Arab",
  },
  {
    code: "hi",
    name: "Hindi",
    nameNative: "हिन्दी",
    flag: "🇮🇳",
    whisper: "hi",
    nllb: "hin_Deva",
  },
];

/** Default source / target languages */
export const DEFAULT_SRC = "vi";
export const DEFAULT_TGT = "en";

/**
 * Look up a language by its code.
 * @param {string} code - Language code (e.g. 'vi', 'en')
 * @returns {object|null}
 */
export function getLanguage(code) {
  return LANGUAGES.find((l) => l.code === code) || null;
}

/**
 * Get valid target languages (all except 'auto' and the current source).
 * @param {string} srcCode - Current source language code
 * @returns {object[]}
 */
export function getTargetLanguages(srcCode) {
  return LANGUAGES.filter((l) => l.code !== "auto" && l.code !== srcCode);
}

/**
 * Get valid source languages (all languages including 'auto').
 * @returns {object[]}
 */
export function getSourceLanguages() {
  return LANGUAGES;
}

/**
 * Persist language selection to localStorage
 */
export function saveLanguagePreference(srcCode, tgtCode) {
  localStorage.setItem("asr_srcLang", srcCode);
  localStorage.setItem("asr_tgtLang", tgtCode);
}

/**
 * Load language selection from localStorage
 * @returns {{ srcCode: string, tgtCode: string }}
 */
export function loadLanguagePreference() {
  return {
    srcCode: localStorage.getItem("asr_srcLang") || DEFAULT_SRC,
    tgtCode: localStorage.getItem("asr_tgtLang") || DEFAULT_TGT,
  };
}

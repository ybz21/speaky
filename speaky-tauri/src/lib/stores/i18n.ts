import { writable, derived } from "svelte/store";

// Translations type
export type Translations = Record<string, string>;

// Available locales
export const locales = ["en", "zh", "zh_TW", "ja", "ko", "de", "fr", "es", "pt", "ru"] as const;
export type Locale = typeof locales[number];

// Default translations (English)
const en: Translations = {
  listening: "Listening...",
  recognizing: "Recognizing...",
  done: "Done!",
  error: "Error",
  no_engine: "No recognition engine configured",
  empty_result: "Recognition result is empty",
  no_audio_detected: "No audio detected, please check your microphone",
  app_name: "Speaky",
  settings: "Settings",
  quit: "Quit",
  settings_title: "Speaky Settings",
  tab_core: "Core",
  tab_engine: "Engine",
  tab_appearance: "Appearance",
  save: "Save",
  cancel: "Cancel",
  hotkey_label: "Hold key:",
  hold_time_label: "Hold delay:",
  seconds: " sec",
  recognition_lang: "Recognition language:",
  audio_device: "Microphone:",
  audio_device_default: "Default device",
  audio_gain: "Microphone gain:",
  streaming_mode: "Streaming mode",
  engine_label: "Engine:",
  api_key: "API Key:",
  base_url: "Base URL:",
  app_key: "App Key:",
  access_key: "Access Key:",
  theme: "Theme:",
  theme_light: "Light",
  theme_dark: "Dark",
  theme_auto: "Auto (System)",
  ui_lang: "Interface language:",
  auto: "Auto (System)",
  window_opacity: "Window opacity:",
};

// Chinese translations
const zh: Translations = {
  listening: "正在录音...",
  recognizing: "识别中...",
  done: "识别完成",
  error: "识别失败",
  no_engine: "未配置识别引擎",
  empty_result: "识别结果为空",
  no_audio_detected: "未检测到声音，请检查麦克风",
  app_name: "语音输入",
  settings: "设置",
  quit: "退出",
  settings_title: "语音输入设置",
  tab_core: "核心",
  tab_engine: "语音识别引擎",
  tab_appearance: "外观",
  save: "保存",
  cancel: "取消",
  hotkey_label: "长按唤醒键:",
  hold_time_label: "长按延迟:",
  seconds: " 秒",
  recognition_lang: "识别语言:",
  audio_device: "麦克风设备:",
  audio_device_default: "默认设备",
  audio_gain: "麦克风增益:",
  streaming_mode: "流式识别",
  engine_label: "引擎:",
  api_key: "API Key:",
  base_url: "Base URL:",
  app_key: "App Key:",
  access_key: "Access Key:",
  theme: "主题:",
  theme_light: "浅色",
  theme_dark: "深色",
  theme_auto: "跟随系统",
  ui_lang: "界面语言:",
  auto: "自动 (跟随系统)",
  window_opacity: "窗口透明度:",
};

const translations: Record<Locale, Translations> = {
  en,
  zh,
  zh_TW: zh, // Fallback to simplified Chinese for now
  ja: en, // Fallback to English
  ko: en,
  de: en,
  fr: en,
  es: en,
  pt: en,
  ru: en,
};

function getSystemLocale(): Locale {
  const lang = navigator.language.toLowerCase();
  if (lang.startsWith("zh")) {
    return lang.includes("tw") || lang.includes("hk") ? "zh_TW" : "zh";
  }
  const primary = lang.split("-")[0];
  return (locales.includes(primary as Locale) ? primary : "en") as Locale;
}

function createI18nStore() {
  const { subscribe, set } = writable<Locale>(getSystemLocale());

  return {
    subscribe,
    setLocale: (locale: Locale | "auto") => {
      if (locale === "auto") {
        set(getSystemLocale());
      } else {
        set(locale);
      }
    },
  };
}

export const locale = createI18nStore();

// Derived translation function
export const t = derived(locale, ($locale) => {
  const trans = translations[$locale] || translations.en;
  return (key: string): string => trans[key] || translations.en[key] || key;
});

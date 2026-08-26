import { derived, writable } from "svelte/store";

/** BCP 47 is the single locale standard used by the UI and persisted config. */
export const supportedLocales = ["zh-CN", "en-US"] as const;
export type Locale = (typeof supportedLocales)[number];

const zhCN = {
  "status.listening": "正在聆听",
  "status.recognizing": "正在识别",
  "status.done": "识别完成",
  "status.error": "识别失败",
  "status.items": "共 {count} 项内容",
  "settings.title": "Speaky 设置",
  "settings.subtitle": "语音输入",
  "settings.group.trigger": "唤醒",
  "settings.group.engine": "引擎",
  "settings.group.language": "界面",
  "settings.interfaceLanguage": "界面语言",
  "settings.hotkey": "长按唤醒键",
  "settings.holdDuration": "长按时长",
  "settings.seconds": "{value} 秒",
  "settings.engine": "识别引擎",
  "engine.volcengine": "火山语音大模型",
  "engine.openai": "OpenAI 语音识别",
  "settings.apiKey": "API Key",
  "settings.apiKeyPlaceholder": "输入 X-Api-Key",
  "settings.openaiApiKeyPlaceholder": "输入 OpenAI API Key",
  "settings.apiKeyHint": "凭证仅保存在本机",
  "settings.cancel": "取消",
  "settings.save": "保存",
  "settings.saving": "保存中…",
  "language.zh-CN": "中文",
  "language.en-US": "英文",
} as const;

export type MessageKey = keyof typeof zhCN;

const enUS: Record<MessageKey, string> = {
  "status.listening": "Listening",
  "status.recognizing": "Recognizing",
  "status.done": "Done",
  "status.error": "Recognition failed",
  "status.items": "{count} items",
  "settings.title": "Speaky Settings",
  "settings.subtitle": "Voice input",
  "settings.group.trigger": "Trigger",
  "settings.group.engine": "Engine",
  "settings.group.language": "Interface",
  "settings.interfaceLanguage": "Interface language",
  "settings.hotkey": "Press-and-hold key",
  "settings.holdDuration": "Hold duration",
  "settings.seconds": "{value} sec",
  "settings.engine": "Recognition engine",
  "engine.volcengine": "Volcengine Speech Model",
  "engine.openai": "OpenAI Transcription",
  "settings.apiKey": "API Key",
  "settings.apiKeyPlaceholder": "Enter X-Api-Key",
  "settings.openaiApiKeyPlaceholder": "Enter OpenAI API Key",
  "settings.apiKeyHint": "Credentials are stored on this device only",
  "settings.cancel": "Cancel",
  "settings.save": "Save",
  "settings.saving": "Saving…",
  "language.zh-CN": "Chinese",
  "language.en-US": "English",
};

const messages: Record<Locale, Record<MessageKey, string>> = {
  "zh-CN": zhCN,
  "en-US": enUS,
};

export function systemLocale(): Locale {
  return navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US";
}

export function normalizeLocale(value: string | null | undefined): Locale {
  if (!value || value === "auto") return systemLocale();
  return value.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US";
}

function createLocaleStore() {
  const { subscribe, set } = writable<Locale>(systemLocale());
  return {
    subscribe,
    setLocale: (value: string) => set(normalizeLocale(value)),
  };
}

export const locale = createLocaleStore();

export const t = derived(locale, ($locale) => {
  return (key: MessageKey, values: Record<string, string | number> = {}): string => {
    return Object.entries(values).reduce(
      (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
      messages[$locale][key],
    );
  };
});

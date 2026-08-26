import { writable } from "svelte/store";
import { invoke } from "@tauri-apps/api/core";

export interface Config {
  core: {
    asr: {
      hotkey: string;
      hotkey_hold_time: number;
      language: string;
      streaming_mode: boolean;
      audio_device: number | null;
      audio_gain: number;
      sound_notification: boolean;
      llm_polish: boolean;
    };
  };
  engine: {
    current: string;
    volc_bigmodel: {
      api_key: string;
      app_key: string;
      access_key: string;
      resource_id: string;
    };
    openai: {
      api_key: string;
      model: string;
      base_url: string;
    };
  };
  appearance: {
    theme: string;
    ui_language: string;
    show_waveform: boolean;
    window_opacity: number;
  };
  llm: {
    openai: {
      api_key: string;
      model: string;
      base_url: string;
    };
  };
  desktop: {
    auto_start: boolean;
  };
}

export const defaultConfig: Config = {
  core: {
    asr: {
      hotkey: "ctrl",
      hotkey_hold_time: 1.0,
      language: "auto",
      streaming_mode: true,
      audio_device: null,
      audio_gain: 1.0,
      sound_notification: true,
      llm_polish: false,
    },
  },
  engine: {
    current: "volc_bigmodel",
    volc_bigmodel: {
      api_key: "",
      app_key: "",
      access_key: "",
      resource_id: "volc.bigasr.sauc.duration",
    },
    openai: {
      api_key: "",
      model: "gpt-4o-transcribe",
      base_url: "https://api.openai.com/v1",
    },
  },
  appearance: {
    theme: "auto",
    ui_language: "zh-CN",
    show_waveform: true,
    window_opacity: 0.9,
  },
  llm: {
    openai: {
      api_key: "",
      model: "gpt-4o-mini",
      base_url: "https://api.openai.com/v1",
    },
  },
  desktop: {
    auto_start: true,
  },
};

function createConfigStore() {
  const { subscribe, set, update } = writable<Config>(defaultConfig);

  return {
    subscribe,

    load: async () => {
      try {
        const config = await invoke<Config>("get_config");
        set(config);
      } catch (e) {
        console.error("Failed to load config:", e);
      }
    },

    save: async (config: Config) => {
      try {
        await invoke("save_config", { config });
        set(config);
      } catch (e) {
        console.error("Failed to save config:", e);
        throw e;
      }
    },

    update: (fn: (config: Config) => Config) => {
      update(fn);
    },
  };
}

export const config = createConfigStore();

use crate::config::Config;
use once_cell::sync::Lazy;
use regex::Regex;
use serde_json::json;
use tokio::runtime::Runtime;

const PROMPT: &str = r#"你是语音转文字润色助手。请润色以下语音识别文本：
1. 修正错别字和同音字错误
2. 合并语音识别产生的错误断句，重新合理分句
3. 去除重复出现的口语冗余词
4. 如果内容包含多个要点或任务，用分点列出
5. 保持原意，代码和英文专有名词不改
6. 直接输出润色后的文本，不要解释

原文："#;

static RUNTIME: Lazy<Runtime> = Lazy::new(|| {
    tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .worker_threads(2)
        .thread_name("speaky-polish")
        .build()
        .expect("failed to create polish runtime")
});

static CLOSED_THINK: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?s)<think>.*?</think>").expect("valid regex"));
static OPEN_THINK: Lazy<Regex> = Lazy::new(|| Regex::new(r"(?s)<think>.*$").expect("valid regex"));

#[derive(Debug, Clone)]
struct Credentials {
    api_key: String,
    model: String,
    base_url: String,
}

fn credentials(config: &Config) -> Option<Credentials> {
    let configured = &config.llm.openai;
    let api_key = std::env::var("SPEAKY_LLM_API_KEY")
        .ok()
        .filter(|value| !value.is_empty())
        .or_else(|| (!configured.api_key.is_empty()).then(|| configured.api_key.clone()))?;
    let base_url = std::env::var("SPEAKY_LLM_BASE_URL")
        .ok()
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| {
            if configured.base_url.is_empty() {
                config.engine.openai.base_url.clone()
            } else {
                configured.base_url.clone()
            }
        });
    let model = std::env::var("SPEAKY_LLM_MODEL")
        .ok()
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| configured.model.clone());
    Some(Credentials {
        api_key,
        model,
        base_url,
    })
}

pub fn is_configured(config: &Config) -> bool {
    credentials(config).is_some()
}

pub fn polish<F>(config: &Config, original: &str, mut on_partial: F) -> Result<String, String>
where
    F: FnMut(&str),
{
    let credentials =
        credentials(config).ok_or_else(|| "LLM API key is not configured".to_string())?;
    RUNTIME.block_on(async move {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(60))
            .build()
            .map_err(|error| error.to_string())?;
        let url = format!(
            "{}/chat/completions",
            credentials.base_url.trim_end_matches('/')
        );
        let mut response = client
            .post(url)
            .bearer_auth(&credentials.api_key)
            .json(&json!({
                "model": credentials.model,
                "messages": [{"role": "user", "content": format!("{}{}", PROMPT, original)}],
                "stream": true
            }))
            .send()
            .await
            .map_err(|error| error.to_string())?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(format!("LLM API error {}: {}", status, body));
        }

        let mut pending = Vec::<u8>::new();
        let mut full = String::new();
        while let Some(chunk) = response.chunk().await.map_err(|error| error.to_string())? {
            pending.extend_from_slice(&chunk);
            while let Some(newline) = pending.iter().position(|byte| *byte == b'\n') {
                let line = pending.drain(..=newline).collect::<Vec<_>>();
                let line = String::from_utf8_lossy(&line);
                let Some(data) = line.trim().strip_prefix("data:") else {
                    continue;
                };
                let data = data.trim();
                if data == "[DONE]" {
                    break;
                }
                if let Ok(value) = serde_json::from_str::<serde_json::Value>(data) {
                    if let Some(delta) = value["choices"][0]["delta"]["content"].as_str() {
                        full.push_str(delta);
                        let cleaned = clean_output(&full);
                        if !cleaned.is_empty() {
                            on_partial(&cleaned);
                        }
                    }
                }
            }
        }

        let cleaned = clean_output(&full);
        if cleaned.is_empty() {
            Err("LLM returned an empty result".to_string())
        } else {
            Ok(cleaned)
        }
    })
}

pub fn clean_output(raw: &str) -> String {
    let mut text = CLOSED_THINK.replace_all(raw, "").trim().to_string();
    text = OPEN_THINK.replace_all(&text, "").trim().to_string();
    if text.len() >= 2 && text.starts_with('"') && text.ends_with('"') {
        text = text[1..text.len() - 1].to_string();
    }
    if text.starts_with('{') {
        if let Ok(value) = serde_json::from_str::<serde_json::Value>(&text) {
            if let Some(extracted) = value.get("text").and_then(|value| value.as_str()) {
                return extracted.to_string();
            }
        }
    }
    text
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn removes_reasoning_and_wrapping() {
        assert_eq!(clean_output("<think>hidden</think>\n\"你好\""), "你好");
        assert_eq!(clean_output(r#"{"text":"hello"}"#), "hello");
    }
}

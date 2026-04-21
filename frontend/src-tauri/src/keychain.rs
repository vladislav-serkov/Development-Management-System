const SERVICE: &str = "com.extractagent.desktop";
const ACCOUNT_API_KEY: &str = "anthropic-api-key";

fn entry() -> Result<keyring::Entry, String> {
    keyring::Entry::new(SERVICE, ACCOUNT_API_KEY).map_err(|e| e.to_string())
}

pub fn read_api_key() -> Option<String> {
    let entry = entry().ok()?;
    match entry.get_password() {
        Ok(key) => Some(key),
        Err(keyring::Error::NoEntry) => None,
        Err(e) => {
            log::warn!("keychain read error: {e}");
            None
        }
    }
}

#[tauri::command]
pub fn has_api_key() -> bool {
    read_api_key().is_some()
}

#[tauri::command]
pub fn save_api_key(key: String) -> Result<(), String> {
    let trimmed = key.trim();
    if trimmed.is_empty() {
        return Err("API key cannot be empty".to_string());
    }
    entry()?
        .set_password(trimmed)
        .map_err(|e| format!("keychain write failed: {e}"))
}

#[tauri::command]
pub fn delete_api_key() -> Result<(), String> {
    let entry = entry()?;
    match entry.delete_credential() {
        Ok(()) => Ok(()),
        Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(format!("keychain delete failed: {e}")),
    }
}

//! Python motorunu (`etkilesim`) alt süreç olarak çalıştırır.
//!
//! Sözleşme: komut adı argv'de, JSON yük stdin'de, yanıt stdout'ta `{ok, data | error}`.
//! Yönetici PIN'i yalnızca `ETKILESIM_ADMIN_PIN` ortam değişkeniyle ve yalnızca o çağrıya
//! verilir; argv'ye veya günlüğe yazılmaz. İş mantığı burada değil, motordadır.

use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};

use serde::Serialize;
use serde_json::Value;

pub const PIN_ENV: &str = "ETKILESIM_ADMIN_PIN";
pub const PARENT_ENV: &str = "ETKILESIM_PARENT_PID";
const SIDECAR_NAME: &str = "etkilesim-engine.exe";

/// Arayüze dönen hata: TypeScript tarafındaki `EngineError {code, message}` ile aynı biçim.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct EngineFailure {
    pub code: String,
    pub message: String,
}

impl EngineFailure {
    pub fn new(code: &str, message: impl Into<String>) -> Self {
        Self { code: code.to_owned(), message: message.into() }
    }

    pub fn internal(message: impl Into<String>) -> Self {
        Self::new("INTERNAL", message)
    }
}

/// Motoru başlatmak için program + ön ek argümanlar.
#[derive(Debug, Clone)]
pub struct EngineLocation {
    pub program: PathBuf,
    pub prefix: Vec<String>,
}

/// Arama sırası: ETKILESIM_ENGINE → uygulama yanındaki paketlenmiş motor → ETKILESIM_PYTHON →
/// (yalnızca debug derlemede) depodaki engine/.venv.
pub fn locate() -> Result<EngineLocation, EngineFailure> {
    if let Some(path) = std::env::var_os("ETKILESIM_ENGINE") {
        return Ok(EngineLocation { program: PathBuf::from(path), prefix: Vec::new() });
    }
    if let Some(dir) = std::env::current_exe().ok().and_then(|exe| exe.parent().map(PathBuf::from)) {
        let sidecar = dir.join(SIDECAR_NAME);
        if sidecar.is_file() {
            return Ok(EngineLocation { program: sidecar, prefix: Vec::new() });
        }
    }
    let module = vec!["-m".to_owned(), "etkilesim".to_owned()];
    if let Some(python) = std::env::var_os("ETKILESIM_PYTHON") {
        return Ok(EngineLocation { program: PathBuf::from(python), prefix: module });
    }
    #[cfg(debug_assertions)]
    {
        let venv = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("engine")
            .join(".venv")
            .join("Scripts")
            .join("python.exe");
        if venv.is_file() {
            return Ok(EngineLocation { program: venv, prefix: module });
        }
    }
    Err(EngineFailure::new(
        "ENGINE_MISSING",
        "Motor bulunamadı: etkilesim-engine.exe uygulamanın yanında olmalı (README → Paketleme).",
    ))
}

/// Pencere açmadan çalışan, PIN taşımayan temel komut.
pub fn base_command(location: &EngineLocation, args: &[&str]) -> Command {
    let mut command = Command::new(&location.program);
    command.args(&location.prefix).args(args).env_remove(PIN_ENV);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    command
}

/// Tek bir motor komutunu çalıştırır (engelleyici; çağıran `spawn_blocking` kullanmalı).
pub fn run(name: &str, payload: &Value, pin: Option<&str>) -> Result<Value, EngineFailure> {
    if !payload.is_object() {
        return Err(EngineFailure::new("VALIDATION", "Yük bir JSON nesnesi olmalı"));
    }
    let location = locate()?;
    let mut command = base_command(&location, &[name]);
    if let Some(pin) = pin.filter(|value| !value.is_empty()) {
        command.env(PIN_ENV, pin);
    }
    command.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());
    let mut child = command
        .spawn()
        .map_err(|error| EngineFailure::internal(format!("Motor başlatılamadı: {error}")))?;
    let body = serde_json::to_vec(payload)
        .map_err(|error| EngineFailure::internal(format!("Yük kodlanamadı: {error}")))?;
    {
        let mut stdin = child
            .stdin
            .take()
            .ok_or_else(|| EngineFailure::internal("Motor girişi açılamadı"))?;
        stdin
            .write_all(&body)
            .map_err(|error| EngineFailure::internal(format!("Motora yazılamadı: {error}")))?;
    } // stdin burada kapanır: motor EOF görür
    let output = child
        .wait_with_output()
        .map_err(|error| EngineFailure::internal(format!("Motor yanıtı okunamadı: {error}")))?;
    parse_response(&output.stdout)
}

/// Motorun stdout'unu ayrıştırır. Biçim dışı yanıt asla "başarılı" sayılmaz.
pub fn parse_response(stdout: &[u8]) -> Result<Value, EngineFailure> {
    let value: Value = serde_json::from_slice(stdout)
        .map_err(|_| EngineFailure::internal("Motor geçersiz yanıt döndürdü (ayrıntı engine.log'da)"))?;
    match value.get("ok").and_then(Value::as_bool) {
        Some(true) => Ok(value.get("data").cloned().unwrap_or(Value::Null)),
        Some(false) => {
            let error = value.get("error");
            let field = |key: &str, fallback: &str| {
                error
                    .and_then(|e| e.get(key))
                    .and_then(Value::as_str)
                    .unwrap_or(fallback)
                    .to_owned()
            };
            Err(EngineFailure { code: field("code", "INTERNAL"), message: field("message", "Bilinmeyen hata") })
        }
        None => Err(EngineFailure::internal("Motor yanıtı beklenen biçimde değil")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn success_returns_data() {
        let out = parse_response(br#"{"ok":true,"data":{"team_id":3}}"#).unwrap();
        assert_eq!(out, json!({"team_id": 3}));
    }

    #[test]
    fn failure_keeps_code_and_message() {
        let err = parse_response(r#"{"ok":false,"error":{"code":"PERMISSION_DENIED","message":"PIN hatalı"}}"#.as_bytes())
            .unwrap_err();
        assert_eq!(err, EngineFailure::new("PERMISSION_DENIED", "PIN hatalı"));
    }

    #[test]
    fn garbage_is_never_success() {
        assert_eq!(parse_response(b"Traceback ...").unwrap_err().code, "INTERNAL");
        assert_eq!(parse_response(br#"{"data":1}"#).unwrap_err().code, "INTERNAL");
        assert_eq!(parse_response(b"").unwrap_err().code, "INTERNAL");
    }

    #[test]
    fn turkish_text_survives() {
        let out = parse_response("{\"ok\":true,\"data\":\"Çok güzel\"}".as_bytes()).unwrap();
        assert_eq!(out, json!("Çok güzel"));
    }

    #[test]
    fn non_object_payload_is_rejected_before_spawning() {
        let err = run("state", &json!([1, 2]), None).unwrap_err();
        assert_eq!(err.code, "VALIDATION");
    }

    /// Gerçek motorla uçtan uca köprü testi (debug derlemede engine/.venv varsa çalışır).
    #[test]
    fn bridge_roundtrip_with_real_engine() {
        if locate().is_err() {
            eprintln!("engine/.venv bulunamadı; köprü testi atlandı");
            return;
        }
        let data = std::env::temp_dir().join(format!("etkilesim-bridge-{}", std::process::id()));
        std::fs::create_dir_all(&data).unwrap();
        std::env::set_var("ETKILESIM_DATA_DIR", &data);

        let health = run("health", &json!({}), None).unwrap();
        assert_eq!(health["author"], "axthrowa");
        run("set-pin", &json!({"new_pin": "246810"}), None).unwrap();
        let denied = run("add-team", &json!({"name": "Çok Ekip"}), None).unwrap_err();
        assert_eq!(denied.code, "PERMISSION_DENIED");
        let wrong = run("add-team", &json!({"name": "Çok Ekip"}), Some("000000")).unwrap_err();
        assert_eq!(wrong.code, "PERMISSION_DENIED");
        let created = run("add-team", &json!({"name": "Çok Ekip"}), Some("246810")).unwrap();
        assert!(created["team_id"].as_i64().unwrap() > 0);
        let state = run("state", &json!({}), None).unwrap();
        assert_eq!(state["teams"][0]["name"], "Çok Ekip");

        let _ = std::fs::remove_dir_all(&data); // geçici test klasörü; silinemezse test sonucu etkilenmez
    }

    #[test]
    fn base_command_never_inherits_the_pin() {
        let location = EngineLocation { program: PathBuf::from("python"), prefix: vec![] };
        let command = base_command(&location, &["state"]);
        let removed = command
            .get_envs()
            .any(|(key, value)| key == PIN_ENV && value.is_none());
        assert!(removed, "PIN ortam değişkeni açıkça kaldırılmalı");
    }
}

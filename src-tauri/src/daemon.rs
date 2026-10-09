//! Zamanlayıcı (`etkilesim daemon`) alt süreci: ölçüm turları, gece uyarı kontrolü, bildirimler.
//!
//! Motor ayrıca üst süreç kimliğini izler; uygulama beklenmedik kapanırsa kendini durdurur.

use std::process::{Child, Stdio};
use std::sync::Mutex;

use tauri::{AppHandle, Manager};

use crate::engine;

#[derive(Default)]
pub struct DaemonState(Mutex<Option<Child>>);

pub fn start(app: &AppHandle) {
    let location = match engine::locate() {
        Ok(location) => location,
        Err(failure) => {
            eprintln!("zamanlayıcı başlatılmadı: {}", failure.message);
            return;
        }
    };
    let mut command = engine::base_command(&location, &["daemon"]);
    command
        .env(engine::PARENT_ENV, std::process::id().to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    match command.spawn() {
        Ok(child) => match app.state::<DaemonState>().0.lock() {
            Ok(mut slot) => *slot = Some(child),
            Err(_) => eprintln!("zamanlayıcı durumu kilitlenemedi"),
        },
        Err(error) => eprintln!("zamanlayıcı başlatılamadı: {error}"),
    }
}

pub fn stop(app: &AppHandle) {
    let state = app.state::<DaemonState>();
    let Ok(mut slot) = state.0.lock() else {
        return;
    };
    if let Some(mut child) = slot.take() {
        // Süreç zaten bitmiş olabilir; her iki durumda da üst süreç bekçisi motoru durdurur.
        if let Err(error) = child.kill() {
            eprintln!("zamanlayıcı sonlandırılamadı: {error}");
        }
        if let Err(error) = child.wait() {
            eprintln!("zamanlayıcı beklenemedi: {error}");
        }
    }
}

//! Arayüzün çağırabileceği motor komutlarının BEYAZ LİSTESİ.
//!
//! Her Tauri komutu tek bir motor komutuna karşılık gelir; genel "her şeyi geçir" komutu yoktur.
//! İş mantığı motordadır; burada yalnızca yönlendirme ve engelleyici işi iş parçacığına alma vardır.

use serde_json::{Map, Value};

use crate::engine::{self, EngineFailure};

async fn dispatch(cli: &'static str, payload: Option<Value>, pin: Option<String>) -> Result<Value, EngineFailure> {
    let body = payload.unwrap_or_else(|| Value::Object(Map::new()));
    tauri::async_runtime::spawn_blocking(move || engine::run(cli, &body, pin.as_deref()))
        .await
        .map_err(|error| EngineFailure::internal(format!("Motor görevi tamamlanamadı: {error}")))?
}

macro_rules! engine_commands {
    ($($name:ident => $cli:literal),* $(,)?) => {
        $(
            #[tauri::command]
            pub async fn $name(payload: Option<Value>, pin: Option<String>) -> Result<Value, EngineFailure> {
                dispatch($cli, payload, pin).await
            }
        )*

        /// (Tauri komutu, motor komutu) çiftleri — testler sözleşmeyi bununla denetler.
        #[cfg(test)]
        pub const ROUTES: &[(&str, &str)] = &[$((stringify!($name), $cli)),*];
    };
}

engine_commands! {
    health => "health",
    state => "state",
    post_detail => "post-detail",
    posting_context => "posting-context",
    add_post => "add-post",
    manual_metrics => "manual-metrics",
    manual_comments => "manual-comments",
    update_note => "update-note",
    refresh => "refresh",
    add_community => "add-community",
    community_state => "community-state",
    settings_get => "settings-get",
    settings_set => "settings-set",
    settings_clear_override => "settings-clear-override",
    verify_pin => "verify-pin",
    set_pin => "set-pin",
    add_team => "add-team",
    update_team => "update-team",
    add_user => "add-user",
    update_user => "update-user",
    discover => "discover",
    strike_check => "strike-check",
    flush => "flush",
    set_telegram_token => "set-telegram-token",
    clear_telegram_token => "clear-telegram-token",
    test_telegram => "test-telegram",
    login_session => "login-session",
    analytics => "analytics",
    community_recommendations => "community-recommendations",
    add_game => "add-game",
    update_game => "update-game",
    add_campaign => "add-campaign",
    update_campaign => "update-campaign",
    archive_post => "archive-post",
    inbox => "inbox",
    inbox_read => "inbox-read",
    set_secret => "set-secret",
    clear_secret => "clear-secret",
    test_email => "test-email",
    test_teams => "test-teams",
    system_overview => "system-overview",
    run_job => "run-job",
    retry_failed => "retry-failed",
    retention => "retention",
    backup => "backup",
    export => "export",
    search => "search",
    seed_demo => "seed-demo",
    metrics => "metrics",
}

#[cfg(test)]
mod tests {
    use super::ROUTES;

    #[test]
    fn every_route_is_the_kebab_case_of_its_command() {
        for (command, cli) in ROUTES {
            assert_eq!(command.replace('_', "-"), *cli);
        }
    }

    #[test]
    fn daemon_is_never_exposed_to_the_ui() {
        assert!(ROUTES.iter().all(|(_, cli)| *cli != "daemon"));
    }

    #[test]
    fn frontend_and_shell_agree_on_command_names() {
        let source = include_str!("../../src/lib/engine.ts");
        for (command, _) in ROUTES {
            assert!(source.contains(&format!("\"{command}\"")), "src/lib/engine.ts '{command}' çağırmıyor");
        }
    }
}

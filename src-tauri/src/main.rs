// Sürüm derlemesinde ek konsol penceresi açılmasın.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! Etkileşim Takip masaüstü kabuğu — created by axthrowa.
//! Kabuk yalnızca istemcidir: pencere + beyaz listeli motor köprüsü + zamanlayıcı yaşam döngüsü.

mod commands;
mod daemon;
mod engine;

fn main() {
    let app = tauri::Builder::default()
        .manage(daemon::DaemonState::default())
        .setup(|app| {
            daemon::start(app.handle());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::health,
            commands::state,
            commands::post_detail,
            commands::posting_context,
            commands::add_post,
            commands::manual_metrics,
            commands::manual_comments,
            commands::update_note,
            commands::refresh,
            commands::add_community,
            commands::community_state,
            commands::settings_get,
            commands::settings_set,
            commands::settings_clear_override,
            commands::verify_pin,
            commands::set_pin,
            commands::add_team,
            commands::update_team,
            commands::add_user,
            commands::update_user,
            commands::discover,
            commands::strike_check,
            commands::flush,
            commands::set_telegram_token,
            commands::clear_telegram_token,
            commands::test_telegram,
            commands::login_session,
            commands::analytics,
            commands::community_recommendations,
            commands::add_game,
            commands::update_game,
            commands::add_campaign,
            commands::update_campaign,
            commands::archive_post,
            commands::inbox,
            commands::inbox_read,
            commands::set_secret,
            commands::clear_secret,
            commands::test_email,
            commands::test_teams,
            commands::system_overview,
            commands::run_job,
            commands::retry_failed,
            commands::retention,
            commands::backup,
            commands::export,
            commands::search,
            commands::seed_demo,
            commands::metrics,
        ])
        .build(tauri::generate_context!());

    match app {
        Ok(app) => app.run(|handle, event| {
            if let tauri::RunEvent::Exit = event {
                daemon::stop(handle);
            }
        }),
        Err(error) => {
            eprintln!("Etkileşim Takip başlatılamadı: {error}");
            std::process::exit(1);
        }
    }
}

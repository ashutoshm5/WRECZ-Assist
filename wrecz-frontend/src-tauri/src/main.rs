// Keep the console attached in dev for backend logs, and hide it in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    wrecz_lib::run()
}

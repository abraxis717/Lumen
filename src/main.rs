use std::io::{self, BufRead};
use tokio::sync::mpsc;

mod app_server;

/// FFI stub: call into the TRM (Text Generation Engine) for actual inference.
///
/// In production this would link to a C shared library or call an
/// external inference server. Here it returns a deterministic stub
/// so that the app server can be validated without a model running.
fn trm_generate(prompt: &str, max_tokens: usize) -> String {
    let word = "generated";
    let tokens: Vec<String> = (0..max_tokens)
        .map(|i| format!("{}_{i}", word))
        .collect();
    format!("[TRM stub] {} {}", prompt, tokens.join(" "))
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let (daemon, rx) = app_server::AppServerDaemon::new(1024);
    let stdout = tokio::io::stdout();

    // Spawn the message processor
    let processor = tokio::spawn(app_server::message_processor(rx, trm_generate));

    // Read from stdin (JSON-RPC requests)
    daemon.run_loop(tokio::io::stdin(), stdout).await?;

    // Drop sender to close channel
    drop(daemon);

    // Wait for processor to finish
    let _ = processor.await;

    Ok(())
}

use serde::{Deserialize, Serialize};
use serde_json::json;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader, Stdin, Stdout};
use tokio::sync::mpsc;
#[derive(Debug, Deserialize, Serialize)]
pub struct JsonRpcMessage {
    pub jsonrpc: Option<String>,
    pub method: Option<String>,
    pub params: Option<serde_json::Value>,
    pub result: Option<serde_json::Value>,
    pub error: Option<serde_json::Value>,
    pub id: Option<serde_json::Value>,
}
pub struct AppServerDaemon {
    incoming_tx: mpsc::Sender<JsonRpcMessage>,
}
impl AppServerDaemon {
    pub fn new(buffer_size: usize) -> (Self, mpsc::Receiver<JsonRpcMessage>) {
        let (tx, rx) = mpsc::channel(buffer_size);
        (AppServerDaemon { incoming_tx: tx }, rx)
    }
    pub async fn run_loop(&self, stdin: Stdin, mut stdout: Stdout) -> Result<(), Box<dyn std::error::Error>> {
        let mut reader = BufReader::new(stdin).lines();
        while let Some(line) = reader.next_line().await? {
            if let Ok(msg) = serde_json::from_str::<JsonRpcMessage>(&line) {
                if self.incoming_tx.try_send(msg).is_err() {
                    let err_frame = json!({
                        "jsonrpc": "2.0",
                        "error": { "code": -32001, "message": "Server overloaded" },
                        "id": null
                    });
                    stdout.write_all(format!("{}\n", err_frame).as_bytes()).await?;
                    stdout.flush().await?;
                }
            } else {
                let parse_err = json!({
                    "jsonrpc": "2.0",
                    "error": { "code": -32700, "message": "Parse error" },
                    "id": null
                });
                stdout.write_all(format!("{}\n", parse_err).as_bytes()).await?;
                stdout.flush().await?;
            }
        }
        Ok(())
    }
}

use serde::{Deserialize, Serialize};
use serde_json::json;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader, Stdin, Stdout};
use tokio::sync::mpsc;
use uuid::Uuid;

// ---------------------------------------------------------------------------
// JSON-RPC 2.0 message types
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize, Serialize)]
pub struct JsonRpcMessage {
    pub jsonrpc: Option<String>,
    pub method: Option<String>,
    pub params: Option<serde_json::Value>,
    pub result: Option<serde_json::Value>,
    pub error: Option<serde_json::Value>,
    pub id: Option<serde_json::Value>,
}

// ---------------------------------------------------------------------------
// Internal state: active threads (conversation sessions)
// ---------------------------------------------------------------------------

#[derive(Debug)]
struct ActiveThread {
    id: String,
    messages: Vec<String>,
}

// ---------------------------------------------------------------------------
// AppServerDaemon: accepts JSON-RPC messages from stdin
// ---------------------------------------------------------------------------

pub struct AppServerDaemon {
    incoming_tx: mpsc::Sender<InternalRequest>,
}

#[derive(Debug)]
pub(crate) enum InternalRequest {
    Initialize { id: Option<serde_json::Value> },
    ThreadStart { params: serde_json::Value, id: Option<serde_json::Value> },
    TurnStart { params: serde_json::Value, id: Option<serde_json::Value> },
    TurnInterrupt { params: serde_json::Value, id: Option<serde_json::Value> },
}

/// Helper: send a JSON-RPC error response.
fn jsonrpc_error(id: Option<serde_json::Value>, code: i64, message: &str) -> serde_json::Value {
    json!({
        "jsonrpc": "2.0",
        "error": { "code": code, "message": message },
        "id": id
    })
}

/// Helper: send a JSON-RPC success response.
fn jsonrpc_success(id: Option<serde_json::Value>, result: serde_json::Value) -> serde_json::Value {
    json!({
        "jsonrpc": "2.0",
        "result": result,
        "id": id
    })
}

/// Write a JSON-RPC response line to stdout.
async fn send_response(
    id: Option<serde_json::Value>,
    code: i64,
    message: &str,
    stdout: &mut Stdout,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let resp = jsonrpc_error(id, code, message);
    stdout
        .write_all(format!("{}\n", serde_json::to_string(&resp)?).as_bytes())
        .await?;
    stdout.flush().await?;
    Ok(())
}

impl AppServerDaemon {
    pub fn new(buffer_size: usize) -> (Self, mpsc::Receiver<InternalRequest>) {
        let (tx, rx) = mpsc::channel(buffer_size);
        (AppServerDaemon { incoming_tx: tx }, rx)
    }

    /// Main event loop: read JSON-RPC lines from stdin, parse, and forward.
    pub async fn run_loop(
        &self,
        stdin: Stdin,
        mut stdout: Stdout,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let mut reader = BufReader::new(stdin).lines();
        while let Some(line) = reader.next_line().await? {
            // Parse JSON-RPC request
            let parsed: JsonRpcMessage = match serde_json::from_str(&line) {
                Ok(msg) => msg,
                Err(_) => {
                    send_response(
                        None,
                        -32700,
                        "Parse error: invalid JSON-RPC",
                        &mut stdout,
                    )
                    .await?;
                    continue;
                }
            };

            // Validate JSON-RPC version
            if parsed.jsonrpc.as_deref() != Some("2.0") {
                send_response(
                    parsed.id.clone(),
                    -32600,
                    "Invalid JSON-RPC version (expected 2.0)",
                    &mut stdout,
                )
                .await?;
                continue;
            }

            // Parse method
            let method = match &parsed.method {
                Some(m) => m.clone(),
                None => {
                    send_response(
                        parsed.id.clone(),
                        -32600,
                        "Invalid request: missing 'method' field",
                        &mut stdout,
                    )
                    .await?;
                    continue;
                }
            };

            // Forward to the message processor
            let request = match method.as_str() {
                "initialize" => InternalRequest::Initialize {
                    id: parsed.id.clone(),
                },
                "thread/start" => InternalRequest::ThreadStart {
                    params: parsed.params.unwrap_or(serde_json::Value::Null),
                    id: parsed.id.clone(),
                },
                "turn/start" => InternalRequest::TurnStart {
                    params: parsed.params.unwrap_or(serde_json::Value::Null),
                    id: parsed.id.clone(),
                },
                "turn/interrupt" => InternalRequest::TurnInterrupt {
                    params: parsed.params.unwrap_or(serde_json::Value::Null),
                    id: parsed.id.clone(),
                },
                unknown => {
                    send_response(
                        parsed.id.clone(),
                        -32601,
                        &format!("Method not found: {}", unknown),
                        &mut stdout,
                    )
                    .await?;
                    continue;
                }
            };

            // Forward with backpressure: reject with -32001 if channel is full
            if self.incoming_tx.send(request).await.is_err() {
                send_response(
                    parsed.id,
                    -32001,
                    "Server overloaded: message queue full",
                    &mut stdout,
                )
                .await?;
            }
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Message processor: handles requests and produces responses
// ---------------------------------------------------------------------------

/// Background task that processes internal requests.
pub async fn message_processor(
    mut rx: mpsc::Receiver<InternalRequest>,
    trm_generate: fn(&str, usize) -> String,
) {
    let mut threads: std::collections::HashMap<String, ActiveThread> =
        std::collections::HashMap::new();

    while let Some(req) = rx.recv().await {
        match req {
            InternalRequest::Initialize { id } => {
                let caps = json!({
                    "protocolVersion": "2.0",
                    "serverInfo": {
                        "name": "lumen_app_server",
                        "version": "0.1.0"
                    },
                    "capabilities": {
                        "threadSupport": true,
                        "turnSupport": true,
                        "interruptSupport": true,
                        "maxTokens": 4096,
                        "maxContextLength": 32768
                    }
                });
                // In a real implementation, we'd write to stdout here.
                // For now, just consume the request.
                let _ = caps;
            }

            InternalRequest::ThreadStart { params, id } => {
                let thread_id = params.get("thread_id")
                    .and_then(|v| v.as_str())
                    .map(|s| s.to_string())
                    .unwrap_or_else(|| Uuid::new_v4().to_string());

                let title = params.get("title")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Untitled");

                let thread = ActiveThread {
                    id: thread_id.clone(),
                    messages: vec![format!("[Thread '{}' started]", title)],
                };

                threads.insert(thread_id.clone(), thread);

                let result = json!({
                    "threadId": thread_id,
                    "status": "created",
                    "title": title
                });
                let _ = result;
            }

            InternalRequest::TurnStart { params, id } => {
                let thread_id = match params.get("thread_id") {
                    Some(t) => t.as_str().unwrap_or("").to_string(),
                    None => {
                        // No thread_id – respond with error
                        let err = jsonrpc_error(id, -32602, "Missing required field: thread_id");
                        let _ = err;
                        continue;
                    }
                };

                let prompt = match params.get("prompt") {
                    Some(p) => p.as_str().unwrap_or("").to_string(),
                    None => {
                        let err = jsonrpc_error(id, -32602, "Missing required field: prompt");
                        let _ = err;
                        continue;
                    }
                };

                let max_tokens = params.get("max_tokens")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(256) as usize;

                // Look up the thread
                let response = if let Some(thread) = threads.get_mut(&thread_id) {
                    thread.messages.push(format!("user: {}", prompt));

                    // Call into TRM via FFI stub
                    let generated = trm_generate(&prompt, max_tokens);
                    thread.messages.push(format!("assistant: {}", generated));

                    json!({
                        "threadId": thread_id,
                        "generated": generated,
                        "messages": thread.messages.clone(),
                        "tokensUsed": max_tokens
                    })
                } else {
                    jsonrpc_error(id, -32002, "Thread not found")
                };

                let _ = response;
            }

            InternalRequest::TurnInterrupt { params, id: _ } => {
                let thread_id = params.get("thread_id")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();

                // Cancel active generation for the thread
                if let Some(thread) = threads.get_mut(&thread_id) {
                    thread.messages.push("[Turn interrupted]".to_string());
                }
            }
        }
    }
}

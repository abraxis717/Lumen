use std::process::Command;
pub struct SandboxManager {
    pub active_profile: String,
    pub workspace_root: String,
}
impl SandboxManager {
    pub fn execute_command(&self, command: &str) -> Result<String, String> {
        let mut bwrap = Command::new("bwrap");
        bwrap
            .arg("--ro-bind").arg("/usr").arg("/usr")
            .arg("--ro-bind").arg("/lib").arg("/lib")
            .arg("--ro-bind").arg("/lib64").arg("/lib64")
            .arg("--proc").arg("/proc")
            .arg("--dev").arg("/dev")
            .arg("--unshare-all")
            .arg("--new-session");
        if self.active_profile == "workspace-write" {
            bwrap.arg("--bind").arg(&self.workspace_root).arg("/workspace")
                 .arg("--chdir").arg("/workspace");
        } else {
            bwrap.arg("--ro-bind").arg(&self.workspace_root).arg("/workspace")
                 .arg("--chdir").arg("/workspace");
        }
        bwrap.arg("sh").arg("-c").arg(command);
        match bwrap.output() {
            Ok(output) if output.status.success() => Ok(String::from_utf8_lossy(&output.stdout).to_string()),
            Ok(output) => Err(String::from_utf8_lossy(&output.stderr).to_string()),
            Err(e) => Err(format!("Sandbox error: {}", e)),
        }
    }
}

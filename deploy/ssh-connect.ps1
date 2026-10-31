# Load deploy/ssh.local.env then open SSH to the OCI instance.
$ErrorActionPreference = "Stop"
$envFile = Join-Path $PSScriptRoot "ssh.local.env"
if (-not (Test-Path $envFile)) {
    Write-Error "Create $envFile from deploy/ssh.local.env.example and set OCI_PUBLIC_IP."
}
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $name, $value = $_ -split '=', 2
    Set-Item -Path "Env:$($name.Trim())" -Value $value.Trim()
}
if (-not $env:OCI_PUBLIC_IP) { Write-Error "Set OCI_PUBLIC_IP in deploy/ssh.local.env" }
if (-not (Test-Path $env:SSH_PRIVATE_KEY)) { Write-Error "Private key not found: $($env:SSH_PRIVATE_KEY)" }
$user = if ($env:SSH_USER) { $env:SSH_USER } else { "ubuntu" }
ssh -o StrictHostKeyChecking=accept-new -i $env:SSH_PRIVATE_KEY "${user}@$($env:OCI_PUBLIC_IP)"

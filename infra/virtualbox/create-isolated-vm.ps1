param(
    [Parameter(Mandatory = $true)]
    [string]$IsoPath,
    [string]$VmName = "nebula-text2sql-docker",
    [string]$VmRoot = "E:\test2\virtualbox",
    [string]$UserName = "text2sql",
    [Parameter(Mandatory = $true)]
    [string]$PasswordFile,
    [switch]$Start,
    [int]$MemoryMb = 6144,
    [int]$CpuCount = 4,
    [int]$DiskMb = 61440
)

$ErrorActionPreference = "Stop"
$vbox = "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
if (-not (Test-Path -LiteralPath $vbox)) { throw "VBoxManage not found: $vbox" }
$iso = (Resolve-Path -LiteralPath $IsoPath).Path
$password = (Resolve-Path -LiteralPath $PasswordFile).Path
$root = [System.IO.Path]::GetFullPath($VmRoot)
$workspace = [System.IO.Path]::GetFullPath("E:\test2") + [System.IO.Path]::DirectorySeparatorChar
if (-not ($root + [System.IO.Path]::DirectorySeparatorChar).StartsWith($workspace, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "VM directory must stay under E:\test2"
}
if (-not $password.StartsWith($workspace, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Password file must stay under E:\test2"
}

$registered = & $vbox list vms
if ($registered -match ('"' + [regex]::Escape($VmName) + '"')) {
    throw "VM '$VmName' already exists. This script refuses to modify an existing VM."
}

New-Item -ItemType Directory -Path $root -Force | Out-Null
& $vbox createvm --name $VmName --ostype Ubuntu_64 --basefolder $root --register
& $vbox modifyvm $VmName --memory $MemoryMb --cpus $CpuCount --ioapic on --firmware efi --nic1 nat
& $vbox modifyvm $VmName --natpf1 "ssh,tcp,127.0.0.1,22222,,22"
& $vbox modifyvm $VmName --natpf1 "web,tcp,127.0.0.1,15173,,15173"
& $vbox modifyvm $VmName --natpf1 "api,tcp,127.0.0.1,18000,,18000"
& $vbox modifyvm $VmName --natpf1 "postgres,tcp,127.0.0.1,15432,,15432"
& $vbox createmedium disk --filename "$root\$VmName\$VmName.vdi" --size $DiskMb --format VDI
& $vbox storagectl $VmName --name SATA --add sata --controller IntelAhci
& $vbox storageattach $VmName --storagectl SATA --port 0 --device 0 --type hdd --medium "$root\$VmName\$VmName.vdi"

$startType = if ($Start) { "headless" } else { "none" }
$postInstall = "apt-get update && apt-get install -y openssh-server docker.io docker-compose-v2 && systemctl enable ssh docker && usermod -aG docker $UserName"
& $vbox unattended install $VmName `
    --iso=$iso `
    --user=$UserName `
    --user-password-file=$password `
    --full-user-name="Nebula Text2SQL" `
    --hostname="nebula-text2sql.local" `
    --locale="en_US" `
    --country="CN" `
    --time-zone="Asia/Shanghai" `
    --package-selection-adjustment=minimal `
    --post-install-command=$postInstall `
    --start-vm=$startType

Write-Host "Created isolated VM '$VmName'. Existing VMs were not changed."
if ($Start) {
    Write-Host "Unattended Ubuntu installation is running headlessly. SSH will be available on 127.0.0.1:22222 after it finishes."
} else {
    Write-Host "Run the VM to begin the prepared unattended installation."
}

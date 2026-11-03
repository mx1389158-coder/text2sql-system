from __future__ import annotations

import argparse
import hashlib
import json
import shlex
from datetime import datetime, timezone
from pathlib import Path

import paramiko


def run(client: paramiko.SSHClient, command: str, timeout: int = 1800) -> str:
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    output = stdout.read().decode("utf-8", errors="replace")
    error = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if code:
        raise RuntimeError(f"remote command failed ({code}): {(output + error).strip()[-4000:]}")
    return output.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup and restore drill in the dedicated VM")
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=22222)
    parser.add_argument("--username", default="text2sql")
    parser.add_argument(
        "--deployment-report",
        type=Path,
        default=Path("infra/virtualbox/deployment-report.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("infra/virtualbox/backup-restore-report.json"),
    )
    args = parser.parse_args()
    password = args.password_file.read_text(encoding="utf-8").strip()
    deployment = json.loads(args.deployment_report.read_text(encoding="utf-8"))
    expected_fingerprint = deployment["ssh_host_key_sha256"]
    if not password:
        raise ValueError("password file is empty")
    if deployment.get("vm") != "nebula-text2sql-docker":
        raise ValueError("deployment report is not for the dedicated Text2SQL VM")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        args.host,
        port=args.port,
        username=args.username,
        password=password,
        timeout=15,
        auth_timeout=15,
    )
    restore_db = "text2sql_restore_drill"
    if restore_db == "text2sql":
        raise AssertionError("restore drill must never target the source database")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    remote_root = f"/home/{args.username}/text2sql-system"
    remote_backup_dir = f"/home/{args.username}/text2sql-backups"
    remote_backup = f"{remote_backup_dir}/text2sql-{timestamp}.dump"
    container_backup = f"/tmp/text2sql-{timestamp}.dump"
    container = ""
    try:
        key = client.get_transport().get_remote_server_key()
        fingerprint = hashlib.sha256(key.asbytes()).hexdigest()
        if fingerprint != expected_fingerprint:
            raise RuntimeError("SSH host key does not match the dedicated VM deployment report")
        container = run(
            client,
            f"cd {shlex.quote(remote_root)} && docker compose ps -q postgres",
        )
        if not container or "\n" in container:
            raise RuntimeError("could not resolve exactly one project PostgreSQL container")
        run(client, f"mkdir -p {shlex.quote(remote_backup_dir)}")
        run(
            client,
            f"docker exec {shlex.quote(container)} pg_dump -U text2sql_admin -d text2sql "
            f"--format=custom --file={shlex.quote(container_backup)}",
        )
        run(
            client,
            f"docker cp {shlex.quote(container)}:{shlex.quote(container_backup)} "
            f"{shlex.quote(remote_backup)}",
        )
        backup_sha256 = run(client, f"sha256sum {shlex.quote(remote_backup)} | cut -d' ' -f1")
        backup_size = int(run(client, f"stat -c %s {shlex.quote(remote_backup)}"))
        run(
            client,
            f"docker exec {shlex.quote(container)} dropdb -U text2sql_admin --if-exists "
            f"--force {restore_db}",
        )
        run(
            client,
            f"docker exec {shlex.quote(container)} createdb -U text2sql_admin {restore_db}",
        )
        run(
            client,
            f"docker exec {shlex.quote(container)} pg_restore -U text2sql_admin "
            f"-d {restore_db} {shlex.quote(container_backup)}",
        )
        table_count = int(
            run(
                client,
                f"docker exec {shlex.quote(container)} psql -U text2sql_admin -d {restore_db} "
                "-Atc \"SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE'\"",
            )
        )
        source_orders = int(
            run(
                client,
                f"docker exec {shlex.quote(container)} psql -U text2sql_admin -d text2sql "
                "-Atc \"SELECT count(*) FROM orders\"",
            )
        )
        restored_orders = int(
            run(
                client,
                f"docker exec {shlex.quote(container)} psql -U text2sql_admin -d {restore_db} "
                "-Atc \"SELECT count(*) FROM orders\"",
            )
        )
        if table_count != 23 or source_orders != restored_orders:
            raise RuntimeError(
                f"restore verification failed: tables={table_count}, "
                f"orders={restored_orders}/{source_orders}"
            )
        status = "passed"
    finally:
        if container:
            try:
                run(
                    client,
                    f"docker exec {shlex.quote(container)} dropdb -U text2sql_admin "
                    f"--if-exists --force {restore_db}",
                )
            except Exception:
                pass
        client.close()

    report = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "vm": "nebula-text2sql-docker",
        "source_database": "text2sql",
        "temporary_restore_database": restore_db,
        "temporary_restore_database_removed": True,
        "backup": {
            "remote_path": remote_backup,
            "sha256": backup_sha256,
            "size_bytes": backup_size,
            "retained": True,
        },
        "verification": {
            "public_table_count": table_count,
            "source_orders": source_orders,
            "restored_orders": restored_orders,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
